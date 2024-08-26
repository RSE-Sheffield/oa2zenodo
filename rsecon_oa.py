import requests, sys

# https://app.oxfordabstracts.com/new-graphql-api-key
OXFORD_ABSTRACTS_API_KEY = 'a5230bcc-4ed0-44bf-8b26-09543321f528' #do not share
OXFORD_ABSTRACTS_API = "https://app.oxfordabstracts.com/v1/graphql"
OXFORD_ABSTRACTS_EVENT_ID = 49081 # RSECon24
# https://graphql-docs.oxfordabstracts.com/
data = {  
  "query":"""
query GetSubmissions($event_id: Int!) {
  events_by_pk(id: $event_id) {
    id
    submissions(where: {decision: {value: {_eq: "Accepted"}}}) {
      decision {
        value
      }
      title {
        submission {
          id
        }
        without_html
      }
      authors {
        first_name
        last_name
        orcid_id
        affiliations {
          institution
        }
        presenting
        title
        email
      }
      accepted_for {
        value
      }
      responses {
        value
        question {
          question_name
        }
      }
      id
    }
  }
}
  """,
  "variables": {"event_id": OXFORD_ABSTRACTS_EVENT_ID},
  "operationName": "GetSubmissions"
}
r = requests.post(OXFORD_ABSTRACTS_API,
                   headers={'x-api-key':OXFORD_ABSTRACTS_API_KEY},
                   json=data
                   )
# Check/Response
response = r.json()
if "errors" in response:
  print("Failed to retrieve submission info")
  print("Status code: %s"%(r.status_code))
  print("Message: %s"%(response["errors"][0]["message"]))
  sys.exit()
  
print(response)
for submission in response["data"]["events_by_pk"]["submissions"]:
    print("Title: %s"%(submission["title"][0]["without_html"]))
    for response in submission["responses"]:
      if response["question"]["question_name"] == "Abstract":          
          print("Abstract: %s"%(response["value"]))#Zenodo permits HTML
          break          
    for author in submission["authors"]:       
        print("Author: %s %s"%(author["first_name"], author["last_name"] ))
        for af in author["affiliations"]:
            print("  %s"%(af["institution"]))
        if author["orcid_id"]:
            print("  %s"%(author["orcid_id"]))
    print("Type: %s"%(submission["accepted_for"]["value"]))
    print("-------------------------------------")