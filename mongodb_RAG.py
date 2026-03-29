import pandas as pd
import pymongo
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
import logging
import os
import json
import requests
import voyageai
from dotenv import load_dotenv
import time
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
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
        self.headers = {
            "x-api-key": self.llm_api_key,
            "Content-Type": "application/json"
        }
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
    def create_embeddings_for_collection(self, days: int = 10):
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        filter = {'$and': [ 
        { 'content': { '$exists': True, "$nin": [ None, "" ] } }, 
        { 'embedding': { '$exists': False } },
        { 'createdTime': { '$gte': cutoff_date.isoformat() } }]} 

        updated_doc_count = 0
        for document in self.collection.find(filter):
            text = document['content']
            embedding = self.get_embedding(text)
            self.collection.update_one({ '_id': document['_id'] }, { "$set": { 'embedding': embedding } }, upsert=True)
            updated_doc_count += 1
            print(f"Processed {updated_doc_count} documents...")

        print("Documents updated: {}".format(updated_doc_count))

####################################################################################################################################
    def get_query_results(self, query: str, limit: int = 5) -> list:

        """Gets results from a vector search query."""
    
        # collection = client["zendesk_ticket"]["Zoho_Ticket"]

        query_embedding = self.get_embedding(query)
        pipeline = [
            {
                    "$vectorSearch": {
                    "index": "vector_index",
                    "queryVector": query_embedding,
                    "path": "embedding",
                    "exact": True,
                    "limit": limit
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

    def llm_integration_chatbot(self, prompt: str):
        body = {"message": 
            {"role": "user", 
            "content": [{"contentType": "text", "body": prompt.strip()}], 
            "model": "claude-v4.5-sonnet"}}
        try:
            r = requests.post(f"{self.llm_api_endpoint}/conversation", headers=self.headers, json=body)
            r.raise_for_status()
            data_res = r.json()
            # print(data_res)
        except requests.exceptions.HTTPError as e:
            print(f"HTTP error: {e}")
            print(f"Response body: {r.text}")
            return f"API Error: {e}"
        except Exception as e:
            print(f"Other error: {e}")
            return f"Error: {e}"
        
        conversation_id = data_res.get('conversationId')
        if not conversation_id:
            return "No conversationId returned from API."

        url = f"{self.llm_api_endpoint}/conversation/{conversation_id}"
        max_retries = 20
        wait_seconds = 2

        # Fetching the result immediately after posting, but the LLM hasn't finished generating yet.
        for attempt in range(max_retries): # This is to handle Time Asychronous issue. 
            try:
                response = requests.get(url, headers={"x-api-key": self.llm_api_key})
                # response.raise_for_status()
                data_result = response.json()
                # print(data_result)

                # More robust way to get the response
                message_keys = list(data_result['messageMap'].keys())
                # print(message_keys)

                if not message_keys:
                    print("No messages found in conversation.")
                    print(f"Attempt {attempt + 1}: Assistant response not ready, retrying in {wait_seconds}s...")
                    time.sleep(wait_seconds)
                
                # Try to get the assistant's response (usually the last message)
                # If there are multiple messages, get the last one (most recent)
                # If there's only one message, that might be the user's message, so return a default
                else:
                    return data_result['messageMap'][message_keys[-1]]['content'][0]['body']
            except requests.exceptions.HTTPError as e:
                print(f"HTTP error: {e}")
                print(f"Response body: {r.text}")
                return f"API Error: {e}"
            except Exception as e:
                print(f"Other error: {e}")
                return f"Error: {e}"
        
    def ask(self, questions: str) ->  str:
        documents = self.get_query_results(questions) # Generate Vector Search Queries

        if not documents:
            return "No relevant tickets found. Try rephrasing your question."

        context = "\n\n".join(documents)
        # Full Prompt
        prompt = f"""You are a helpful support assistant analyzing Zendesk tickets.
        Use ONLY the following ticket data to answer the question.
        If the answer isn't in the context, say 'I don't have enough information.'

        Context:
        {context}

        Question: {questions}
        Answer:"""
        return self.llm_integration_chatbot(prompt)
        
        
# if __name__ == "__main__":
#     main()