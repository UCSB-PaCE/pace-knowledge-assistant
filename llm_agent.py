import requests
import time
import os
from typing import Any, Optional
from langchain_core.language_models.llms import LLM
from langchain_core.callbacks.manager import CallbackManagerForLLMRun

class SandBoxLLM(LLM):

    llm_api_endpoint: str
    llm_api_key: str
    model: str = "claude-v4.5-sonnet"
    max_retries: int = 20
    wait_seconds: int = 2


    @property
    def _llm_type(self) -> str:
        return "sandbox_llm"


    def _call(self,prompt: str, **kwargs: Any) -> str:
        """
        Required method — LangChain calls this with the prompt,
        expects a plain string back.
        This is where your existing _call_llm logic lives.
        """
        headers = {
            "x-api-key": self.llm_api_key,
            "Content-Type": "application/json"
        }

        body = {
            "message": {
                "role": "user",
                "content": [{"contentType": "text", "body": prompt.strip()}],
                "model": self.model
            }
        }

        try:
            r = requests.post(
                f"{self.llm_api_endpoint}/conversation",
                headers=headers,
                json=body
            )
            r.raise_for_status()
            data_res = r.json()
        except Exception as e:
            return f"Error sending message: {e}"

        conversation_id = data_res.get('conversationId')
        if not conversation_id:
            return "No conversationId returned."

        url = f"{self.llm_api_endpoint}/conversation/{conversation_id}"

        for attempt in range(self.max_retries):
            try:
                response = requests.get(url, headers={"x-api-key": self.llm_api_key})
                data_result = response.json()
                message_keys = list(data_result.get('messageMap', {}).keys())

                for key in reversed(message_keys):
                    message = data_result['messageMap'][key]
                    if message.get('role') == 'assistant':
                        return message['content'][0]['body']

                time.sleep(self.wait_seconds)

            except Exception as e:
                print(f"GET error attempt {attempt + 1}: {e}")
                time.sleep(self.wait_seconds)

        return "Timed out waiting for response."