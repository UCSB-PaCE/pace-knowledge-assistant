from pymongo.mongo_client import MongoClient
from pymongo.operations import SearchIndexModel
import time
import os
from dotenv import load_dotenv

# Connect to your deployment
load_dotenv()

## Connect to MongoDB and set up the collection
mongodb_connection = os.getenv("MongoDB_Client")
client = MongoClient(mongodb_connection)
collection = client["zendesk_ticket"]["Zoho_Ticket"]

index_name = "vector_index"
search_index_model = SearchIndexModel(
  definition = {
    "fields": [
      {
        "type": "vector",
        "numDimensions": 1024,
        "path": "embedding",
        "similarity": "cosine"
      }
    ]
  },
  name = index_name,
  type = "vectorSearch"
)
collection.create_search_index(model=search_index_model)

print("Polling to check if the index is ready. This may take up to a minute.")
predicate=None
if predicate is None:
   predicate = lambda index: index.get("queryable") is True
while True:
   indices = list(collection.list_search_indexes(index_name))
   if len(indices) and predicate(indices[0]):
      break
   time.sleep(5)
print(index_name + " is ready for querying.")

client.close()
