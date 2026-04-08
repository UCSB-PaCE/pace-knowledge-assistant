import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests
from langchain_core.language_models.llms import LLM


@dataclass(frozen=True)
class AdaptivePollingConfig:
    # I pulled these defaults from the LLM Sandbox adaptive polling guidance.
    # The big point is that polling on a rigid fixed cadence is exactly how we 
    # accidentally create unnecessary pressure get 429s.
    """Polling defaults taken from the LLM Sandbox adaptive polling guide.

    The guide recommends starting quickly at 300ms, then backing off by 1.5x
    until a 5 second ceiling. That gives low latency for fast responses while
    avoiding the fixed tight loop that commonly triggers 429 responses.
    """

    initial_interval_seconds: float = 0.3
    backoff_factor: float = 1.5
    max_interval_seconds: float = 5.0
    max_retries: int = 5
    request_timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> "AdaptivePollingConfig":
        # I still want this configurable without code edits, so every important
        # dial can be overridden from .env. The defaults match the guide, and the
        # guards below stop obviously bad values from breaking the polling logic.
        initial_ms = float(os.getenv("LLMSANDBOX_POLL_INITIAL_MS", "300"))
        max_ms = float(os.getenv("LLMSANDBOX_POLL_MAX_MS", "5000"))
        backoff_factor = float(os.getenv("LLMSANDBOX_POLL_BACKOFF_FACTOR", "1.5"))
        max_retries = int(os.getenv("LLMSANDBOX_POLL_MAX_RETRIES", "5"))
        request_timeout_seconds = int(os.getenv("LLMSANDBOX_REQUEST_TIMEOUT_SECONDS", "30"))

        return cls(
            initial_interval_seconds=max(0.1, initial_ms / 1000),
            backoff_factor=max(1.0, backoff_factor),
            max_interval_seconds=max(0.1, max_ms / 1000),
            max_retries=max(1, max_retries),
            request_timeout_seconds=max(1, request_timeout_seconds),
        )

class SandBoxLLM(LLM):
    # I kept the LangChain wrapper, but moved the API behavior into explicit helper
    # methods so the request lifecycle is readable: create conversation, poll for
    # completion, slow down when the service tells us to slow down.

    llm_api_endpoint: str
    llm_api_key: str
    model: str = "claude-v4.5-sonnet"
    polling_config: AdaptivePollingConfig = AdaptivePollingConfig.from_env()


    @property
    def _llm_type(self) -> str:
        return "sandbox_llm"

    @property
    def headers(self) -> dict[str, str]:
        # I centralize headers here so POST requests all stay consistent and I do
        # not have little header dicts duplicated around the file.
        return {
            "x-api-key": self.llm_api_key,
            "Content-Type": "application/json"
        }

    def generate_response(self, prompt: str) -> str:
        # I exposed a plain helper so callers outside LangChain can use the exact
        # same adaptive polling behavior without duplicating transport logic.
        return self._call(prompt)

    def _next_interval(self, current_interval: float) -> float:
        # This is the heart of the backoff rule from the guide:
        # next_interval = min(current_interval * backoff_factor, max_interval)
        # In practice that means we start responsive, but each miss makes us a bit
        # more patient so we stop hammering the API.
        return min(
            current_interval * self.polling_config.backoff_factor,
            self.polling_config.max_interval_seconds,
        )

    def _sleep_after_429(self, current_interval: float, stage: str) -> float:
        # When we get a 429, I do not want to blindly sleep some magic constant.
        # Since Sandbox does not clearly document Retry-After as a contract, I am
        # intentionally using only our own adaptive interval here.
        # After sleeping, I still back off again so repeated 429s progressively
        # reduce our request rate.
        sleep_seconds = min(current_interval, self.polling_config.max_interval_seconds)

        print(
            f"LLM Sandbox rate limited during {stage}; sleeping {sleep_seconds:.2f}s before retrying."
        )
        time.sleep(sleep_seconds)
        return self._next_interval(max(current_interval, sleep_seconds))

    def _extract_assistant_message(self, data_result: dict[str, Any]) -> Optional[str]:
        # Conversation payloads can contain multiple messages, including the user
        # message we just sent. I walk backward so I can grab the newest assistant
        # reply rather than accidentally echoing user content back to the caller.
        message_map = data_result.get("messageMap", {})
        message_keys = list(message_map.keys())

        for key in reversed(message_keys):
            message = message_map.get(key, {})
            if message.get("role") != "assistant":
                continue

            content = message.get("content") or []
            if content and content[0].get("body"):
                return content[0]["body"]

        return None

    def _start_conversation(self, body: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        # I separate conversation creation from result polling because the rate
        # limiting story applies to both stages independently. POST can get rate
        # limited, and GET can get rate limited, so each needs its own retry path.
        interval = self.polling_config.initial_interval_seconds

        for attempt in range(1, self.polling_config.max_retries + 1):
            try:
                response = requests.post(
                    f"{self.llm_api_endpoint}/conversation",
                    headers=self.headers,
                    json=body,
                    timeout=self.polling_config.request_timeout_seconds,
                )
            except requests.RequestException as error:
                # Transient network failures should slow us down slightly too.
                # Retrying instantly after a timeout or connection hiccup is not
                # materially different from spamming the service.
                if attempt == self.polling_config.max_retries:
                    return None, f"Error sending message: {error}"

                print(f"Conversation creation attempt {attempt} failed: {error}")
                time.sleep(interval)
                interval = self._next_interval(interval)
                continue

            if response.status_code == 429:
                # A 429 here means we are being told to back off before the
                # conversation was even accepted, so I use the same adaptive
                # slowdown pattern instead of failing immediately.
                if attempt == self.polling_config.max_retries:
                    return None, "LLM Sandbox rate limit exceeded while creating the conversation."

                interval = self._sleep_after_429(interval, "conversation creation")
                continue

            try:
                response.raise_for_status()
                data_res = response.json()
            except requests.RequestException as error:
                return None, f"Error sending message: {error}"

            conversation_id = data_res.get("conversationId")
            if conversation_id:
                # Once I have the conversation id, I stop retrying POST entirely
                # and move into the polling phase.
                return conversation_id, None

            return None, "No conversationId returned."

        return None, "LLM Sandbox did not accept the conversation request."

    def _poll_for_completion(self, conversation_id: str) -> str:
        # Polling is where the old code was most likely to create 429s. The issue
        # was not just polling, it was polling on a fixed interval with no notion
        # of adaptive slowdown. This loop starts quickly, then backs off every
        # time the assistant is not ready yet.
        url = f"{self.llm_api_endpoint}/conversation/{conversation_id}"
        interval = self.polling_config.initial_interval_seconds

        for attempt in range(1, self.polling_config.max_retries + 1):
            try:
                response = requests.get(
                    url,
                    headers={"x-api-key": self.llm_api_key},
                    timeout=self.polling_config.request_timeout_seconds,
                )
            except requests.RequestException as error:
                # I treat transient GET failures like a signal to pause and try
                # again later rather than stack more requests on top of a shaky
                # connection or a busy upstream.
                if attempt == self.polling_config.max_retries:
                    return f"Timed out waiting for response: {error}"

                print(f"Polling attempt {attempt} failed: {error}")
                time.sleep(interval)
                interval = self._next_interval(interval)
                continue

            if response.status_code == 429:
                # Same idea as POST handling: if the service says we are polling
                # too aggressively, I slow down here instead of keeping the old
                # cadence and making the problem worse.
                if attempt == self.polling_config.max_retries:
                    return "LLM Sandbox rate limit exceeded while polling for the assistant response."

                interval = self._sleep_after_429(interval, "response polling")
                continue

            try:
                response.raise_for_status()
                data_result = response.json()
            except requests.RequestException as error:
                return f"Timed out waiting for response: {error}"

            assistant_message = self._extract_assistant_message(data_result)
            if assistant_message:
                # This is the success path: as soon as the assistant reply exists,
                # I return it immediately instead of doing any extra sleeps.
                return assistant_message

            if attempt == self.polling_config.max_retries:
                break

            # I intentionally sleep after an empty poll result because an empty
            # response is not a failure, it just means generation is still in
            # progress. Starting at 300ms keeps fast completions snappy, and the
            # growing interval keeps us from turning that wait into a 429 problem.
            time.sleep(interval)
            interval = self._next_interval(interval)

        return "Timed out waiting for response."


    def _call(self,prompt: str, **kwargs: Any) -> str:
        """
        Required method — LangChain calls this with the prompt,
        expects a plain string back.
        This is where your existing _call_llm logic lives.
        """
        # I keep the request body construction here because this is the one place
        # where the actual user prompt becomes an LLM Sandbox conversation.
        body = {
            "message": {
                "role": "user",
                "content": [{"contentType": "text", "body": prompt.strip()}],
                "model": self.model
            }
        }

        # Step 1: create the async conversation.
        conversation_id, error = self._start_conversation(body)
        if error:
            return error
        if conversation_id is None:
            return "No conversationId returned."

        # Step 2: poll for the assistant result using adaptive backoff.
        return self._poll_for_completion(conversation_id)