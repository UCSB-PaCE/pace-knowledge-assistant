import json
import os
from typing import Optional, List
from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from llm_agent import SandBoxLLM
from dotenv import load_dotenv


class TicketQueryIntent(BaseModel):
    """
    What the intent agent returns.
    Every field has a default so it's always safe to use downstream
    even if the LLM can't extract a specific field.
    """
    days: int = Field(
        default=10,
        description="Number of days to look back (e.g. 'last 30 days', 'past month' → 30)"
    )
    limit: int = Field(
        default=10,
        description="Number of tickets to retrieve",
        ge=1,
        le=50    # cap at 50 to protect LLM context window
    )
    # program: Optional[List[str]] = Field(
    #     default=None,
    #     description="List of program names to filter by for MongoDB"
    # )
    summary_type: str = Field(
        default="general",
        description="Type of output: general, email summary, report, overview"
    )

class IntentExtractionAgent:
    # PROGRAMS = [
    #     "Professional Postgraduate Program (PPP)", "Python Programming",
    #     "Behavior Supports and Systems", "Customized Programs",
    #     "Educational Partnerships", "Web Development", "Project Management",
    #     "Step UPP", "Degree Completion", "Semiconductor Manufacturing",
    #     "Top College", "Strategic Investment",
    #     "Business Communication and Law", "Quickstart",
    #     "Accounting and Finance", "GROW",
    #     "Technology Management Program (TMP)",
    #     "Optional Practical Training (OPT)", "Business Leadership",
    #     "EMT", "Digital Marketing", "Infrared",
    #     "University Immersion Program", "GAPP",
    #     "Human Resource Management", "International Certificate Program",
    #     "Hospitality", "Registered Behaviour Technician",
    #     "Global Business", "Visiting Scholars", "BCBA", "QBA",
    #     "QASP", "Applied AI and Innovation", "Paralegal Studies",
    #     "Degree Plus", "International Certificate/Diploma Program",
    #     "BCaBA", "UCSB Master Scholar Summer Research", "EVT",
    #     "KSE Global Connect", "Child Life", "Blockchain Academy",
    #     "Open University", "Business Administration"]

    def __init__(self):
        load_dotenv()

        self.llm = SandBoxLLM(
            llm_api_endpoint=os.getenv("LLMSANDBOX_API_ENDPOINT"),
            llm_api_key=os.getenv("LLMSANDBOX_API_KEY")
        )
        # self.headers = {
        #     "x-api-key": self.llm_api_key,
        #     "Content-Type": "application/json"
        # }

        self.parser = JsonOutputParser(pydantic_object=TicketQueryIntent)

        self.prompt = PromptTemplate(template=
                """You are a precise query parser for a Zoho ticket system.
                Your only job is to extract structured search parameters from user questions.
                Always apply sensible defaults when information is not explicitly stated.
            
                Read the user's question carefully.
                Extract the time range if mentioned (e.g. 'last 30 days' → days=30).
                Extract the number of tickets if mentioned (e.g. '20 tickets' → limit=20).
                Apply defaults for anything not mentioned."

                output_instructions:
                Return ONLY the structured intent — no explanation needed.
                Extract search parameters from the user's question and return ONLY valid JSON.
                No markdown, no explanation, no code fences — raw JSON only.

                Cap limit at 50 maximum regardless of what user requests.
                If no time range is mentioned, default to 10 days.
                Common time mappings: 'last week'=7, 'last month'=30, 'last quarter'=95

                Also noted that, Internatioanl Program can refer to "International Certificate Program", "International Certificate/Diploma Program", 
                "University Immersion Program", "GAPP", and "Step UPP".

                Board Certified Behavior Analyst can refer to "BCBA", "BCaBA", and "Registered Behaviour Technician".

                User question: {question}
        """, 
            input_variables=["question"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            })

        self.chain = self.prompt | self.llm | self.parser
       

    def extract(self, question: str) -> TicketQueryIntent:
        """
        Runs the full chain and returns a validated TicketQueryIntent.
        Falls back to safe defaults if anything fails.
        """
        try:
            result = self.chain.invoke({"question": question})
            # result is a dict from JsonOutputParser — validate with Pydantic
            return TicketQueryIntent(**result)
        except Exception as e:
            print(f"Intent extraction failed: {e}, using defaults.")
            return TicketQueryIntent()  # safe defaults always work