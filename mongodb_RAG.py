from pymongo import MongoClient
import os
import voyageai
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from intent_agent import TicketQueryIntent
from llm_agent import SandBoxLLM
# Load the embedding model (https://huggingface.co/mixedbread-ai/mxbai-embed-large-v1)
# load_dotenv()

class ZohoTicket:
    def __init__(self, collection_name: str = "Zoho_Ticket"):
        load_dotenv()

        # MongoDB connection
        self.client = MongoClient(os.getenv("MongoDB_Client"))
        self.collection = self.client["zendesk_ticket"][collection_name]

        # Voyage AI Client
        self.vo = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
        self.model = "voyage-4" # Voyage AI

        # LLM SandBox API 
        self.llm_api_endpoint = os.getenv("LLMSANDBOX_API_ENDPOINT")
        self.llm_api_key = os.getenv("LLMSANDBOX_API_KEY")
        # I intentionally route all LLM Sandbox traffic through the shared client
        # now, because I only want one implementation of the polling/rate-limit
        # behavior in this repo. That keeps the intent agent and the chatbot from
        # drifting into different retry strategies.
        self.llm = SandBoxLLM(
            llm_api_endpoint=self.llm_api_endpoint,
            llm_api_key=self.llm_api_key,
        )

        from intent_agent import IntentExtractionAgent
        self.intent_agent = IntentExtractionAgent()
# ## Connect to MongoDB and set up the collection
# mongodb_connection = os.getenv("MongoDB_Client")
# client = MongoClient(mongodb_connection)
# collection = client["zendesk_ticket"]["Zoho_Ticket"]

# model = "voyage-4" # Voyage AI
# vo = voyageai.Client(
#     api_key=os.getenv("VOYAGE_API_KEY")
# )

# LLM_API_ENDPOINT = os.getenv("LLMSANDBOX_API_ENDPOINT")
# LLM_API_KEY = os.getenv("LLMSANDBOX_API_KEY")

# headers = {
#     "x-api-key": LLM_API_KEY,
#     "Content-Type": "application/json"
# }
# print(os.getenv("Voyage_API_KEY"))

    # Define a function to generate embeddings
    def get_embedding(self, data) -> list:
        embeddings = self.vo.embed(data, model = self.model).embeddings
        return embeddings[0]

    # Calculate the cutoff date (10 days ago) --> Subject to Change (Hopefully embed with user's prompt, right now just static 10 days)

    # Filters for only documents with a content field and without an embedding field, within last 10 days

    # Creates embeddings for all matching documents (no limit) - Purpose is to store embeddings in the collection 

####################################################################################################################################
    def get_query_results(self, query: str, intent: TicketQueryIntent) -> list:

        """Gets results from a vector search query."""
    
        # collection = client["zendesk_ticket"]["Zoho_Ticket"]

        query_embedding = self.get_embedding(query)

        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

        vector_filter = {
            "createdTime": {"$gte": cutoff_date}
        }

        # if intent.program:
        #     if len(intent.program) == 1:
        #         # Single program — use $eq
        #         vector_filter["program"] = {"$eq": intent.program[0]}
        #     else:
        #         # Multiple programs — use $in
        #         vector_filter["program"] = {"$in": intent.program}

        pipeline = [
            {
                    "$vectorSearch": {
                    "index": "vector_index",
                    "queryVector": query_embedding,
                    "path": "embedding",
                    "exact": True,
                    "limit": intent.limit, 
                    "filter": vector_filter
                    }
            }, 
                {
                    "$project": {
                        "_id": 0,
                        "email": 1,
                        "createdTime": 1,
                        "createdTimeDate": 1,
                        "subject": 1,
                        "program": 1,
                        "content": 1,
                        "closedTime": 1,
                        "score": {"$meta": "vectorSearchScore"}
                    }
                }
        ]
        results = list(self.collection.aggregate(pipeline))
        emails = [item['content'] for item in results]
        # print(len(emails))
        return emails
    
    def llm_integration_chatbot(self, prompt: str) -> str:
        # I used to have a second copy of the conversation POST/GET logic here.
        # That was a maintenance problem and a rate-limit problem, because one
        # path could be fixed while the other still behaved badly. Now the chatbot
        # uses the same adaptive polling client as everything else.
        return self.llm.generate_response(prompt)

    
        
    def ask(self, questions: str) ->  tuple[str, TicketQueryIntent]:

        intent = self.intent_agent.extract(questions)

        # program_display = (
        # ", ".join(intent.program) if intent.program else "All programs")

        # print(f"Detected intent: days={intent.days}, limit={intent.limit}, "
        #   f"program={program_display}, summary_type={intent.summary_type}")

        documents = self.get_query_results(questions, intent) # Generate Vector Search Queries

        if not documents:
            return "No relevant tickets found. Try rephrasing your question.", intent

        context = "\n\n".join(documents)
        # Full Prompt
        prompt = f"""You are a helpful support assistant analyzing Zoho tickets.
        Use ONLY the following ticket data to answer the question.
        If the answer isn't in the context, say 'I don't have enough information.'

        Please  generalize or summarize the insights instead of singling out each individual ticket unless specifiied. 

        Output format: {intent.summary_type}

        Ticket Data ({len(documents)} tickets from last {intent.days} days

        {context}

        Question: {questions}
        Answer:"""
        return self.llm_integration_chatbot(prompt), intent
        
        
# if __name__ == "__main__":
#     main()