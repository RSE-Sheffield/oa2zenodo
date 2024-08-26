import requests, sys, configparser, csv

# Load config file
if len(sys.argv) > 2:
    print("Script requires a maximum of 1 argument, specifying the config file, %d were provided"%(len(sys.argv)-1))
    print("rsecon24.ini will be attempted if an argument is not provided."
    sys.exit()
    
conf_path = "rsecon24.ini" if len(sys.argv)==1 else sys.argv[1]
conf = configparser.ConfigParser()
if os.path.exists(conf_path): 
    with open(conf_path, "r") as conf_file: 
        conf.read_file(conf_file) 
else:
    print(f"The config file '{conf_path}' was not found.")
    sys.exit()

# Validate config file has required sections/keys
REQUIRED_SECTIONS = {'OXFORD_ABSTRACTS', 'ZENODO'}
if not REQUIRED_SECTIONS.issubset(conf.sections()):
    print("Config requires sections: %s"%(REQUIRED_SECTIONS))
    sys.exit()
REQUIRED_OA_KEYS = {'api_key', 'event_id'}
if not REQUIRED_OA_KEYS.issubset(conf['OXFORD_ABSTRACTS'].keys():
    print("Config 'OXFORD_ABSTRACTS' section requires keys: %s"%(REQUIRED_OA_KEYS))
    sys.exit()
REQUIRED_Z_KEYS = {'api_key', 'community_identifiers', 'conference_title', 'conference_acronym', 'conference_dates', 'conference_place', 'conference_url'}
if not REQUIRED_Z_KEYS.issubset(conf['ZENODO'].keys():
    print("Config 'ZENODO' section requires keys: %s"%(REQUIRED_Z_KEYS))
    sys.exit()

# Fetch submission info from OA
# https://app.oxfordabstracts.com/new-graphql-api-key
OXFORD_ABSTRACTS_API = "https://app.oxfordabstracts.com/v1/graphql"
FETCH_SUBMISSIONS_QUERY = {  
  "query":"""
query FetchSubmissions($event_id: Int!) {
  events_by_pk(id: $event_id) {
    id
    submissions(where: {decision: {value: {_eq: "Accepted"}}}) {
      decision {
        value
      }
      title {
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
  "variables": {"event_id": conf.get('OXFORD_ABSTRACTS', 'event_id')},
  "operationName": "FetchSubmissions"
}
try:
  r = requests.post(OXFORD_ABSTRACTS_API,
      headers={'x-api-key':conf.get('OXFORD_ABSTRACTS', 'api_key')},
      json=FETCH_SUBMISSIONS_QUERY
      )
  response = r.json()    
  if "errors" in response:
      print(f"Failed to fetch submission data from Oxford Abstracts:\n{response["errors"][0]["message"]}")
      sys.exit()
except Exception as e:
      print(f"An {type(e)} was thrown whilst fetching submission data from Oxford Abstracts:\n{e.message}")
      sys.exit()

oa_submissions = response["data"]["events_by_pk"]["submissions"]

class Author:
  first=""
  last=""
  orcid=None
  institutions=[]
  
# Create output file to log progress of records
with open('oa2zenodo_log.csv', 'w', newline='') as logfile:
    log = csv.writer(csvfile, dialect='excel')
    # Write header
    log.writerow(['submission_id', 'submission_title', 'doi', 'status'])    
    # Process submissions
    for submission in oa_submissions:
        sub_doi = ''
        sub_id = submission["id"]
        sub_title = submission["title"][0]["without_html"]
        sub_abstract = "" # Zenodo permits HTML
        sub_approve_upload = False
        sub_authors = []
        # Locate responses (abstract, upload_approval)
        for response in submission["responses"]:
          if response["question"]["question_name"] == "Abstract":
              sub_abstract = response["value"]
              continue
        # Extract author detail
        for author in submission["authors"]:
            a = Author()
            a.first = author["first_name"]
            a.last = author["last_name"]
            for af in author["affiliations"]:
                a.institutions.append(af["institution"])
            if author["orcid_id"]:
                a.orcid = author["orcid_id"]
            sub_authors.append(a)
        try:
          # Create Zenodo draft record
          #sub_doi = 
        except Exception as e:
            # Update log
            log.writerow([sub_id, sub_title, sub_doi, f"Zenodo draft creation failed: {e.message()}"])
            continue
          # User input to locate files
          
        try:
          # Upload and attach files to Zenodo record
        except Exception as e:
            # Update log
            log.writerow([sub_id, sub_title, sub_doi, f"Uploading files to Zenodo failed: {e.message()}"])
            continue
          
        try:
          # Publish
        except Exception as e:
            # Update log
            log.writerow([sub_id, sub_title, sub_doi, f"Publishing complete Zenodo draft failed: {e.message()}"])
            continue
        # Update log
        #log.writerow([sub_id, sub_title, sub_doi, "Zenodo record published" if ?? else "Zenodo draft created"])
    