import requests, sys, configparser, csv, os
from collections import defaultdict

# Load config file
if len(sys.argv) > 2:
    print("Script requires a maximum of 1 argument, specifying the config file, %d were provided"%(len(sys.argv)-1))
    print("rsecon24.ini will be attempted if an argument is not provided.")
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
if not REQUIRED_OA_KEYS.issubset(conf['OXFORD_ABSTRACTS'].keys()):
    print("Config 'OXFORD_ABSTRACTS' section requires keys: %s"%(REQUIRED_OA_KEYS))
    sys.exit()
REQUIRED_Z_KEYS = {'api_key', 'use_sandbox', 'draft_only', 'keywords', 'community_identifiers', 'conference_title', 'conference_acronym', 'conference_dates', 'conference_place', 'conference_url'}
if not REQUIRED_Z_KEYS.issubset(conf['ZENODO'].keys()):
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
      print(f"Failed to fetch submission data from Oxford Abstracts:\n{response['errors'][0]['message']}")
      sys.exit()
except Exception as e:
      print(f"An {type(e)} was thrown whilst fetching submission data from Oxford Abstracts:\n{e.message}")
      sys.exit()

oa_submissions = response["data"]["events_by_pk"]["submissions"]

FETCH_PROGRAMME_QUERY = {  
  "query":"""
query FetchProgramme($event_id: Int!) {
  events_by_pk(id: $event_id) {
    program_dates {
      program_sessions {
        name
        program_sessions_submissions {
          submission {
            title {
              without_html
            }
          }
          submission_id
        }
        colour
        program_sessions_program_columns {
          program_column {
            name
          }
        }
        end_time
        start_time
      }
      program_date
    }
  }
}
""",
  "variables": {"event_id": conf.get('OXFORD_ABSTRACTS', 'event_id')},
  "operationName": "FetchProgramme"
}
try:
  r = requests.post(OXFORD_ABSTRACTS_API,
      headers={'x-api-key':conf.get('OXFORD_ABSTRACTS', 'api_key')},
      json=FETCH_PROGRAMME_QUERY
      )
  response = r.json()    
  if "errors" in response:
      print(f"Failed to fetch programme data from Oxford Abstracts:\n{response['errors'][0]['message']}")
      sys.exit()
except Exception as e:
      print(f"An {type(e)} was thrown whilst fetching programme data from Oxford Abstracts:\n{e.message}")
      sys.exit()

oa_programme_dates_raw = response["data"]["events_by_pk"]["program_dates"]

# Process raw graphql response into a cleaner format
class ProgrammeItem:
    def __init__(self, date, start_time, end_time, session_name, track_name):
        self.date = date # do we want to parse this to a proper object?
        self.start_time = start_time # do we want to parse this to a proper object?
        self.end_time = end_time # do we want to parse this to a proper object?
        self.session_name = session_name
        self.track_name = track_name

    def __str__(self):
        return f"Prog(Date:{self.date}, Time:{self.start_time}-{self.end_time}, Session: {self.session_name}, Track: {self.track_name})"

oa_programme_submissions = defaultdict(list)
oa_programme_plenary = [] # Not strictly plenary, sessions without a submission or column
for programme_date in oa_programme_dates_raw:
    date = programme_date["program_date"]
    for programme_session in programme_date["program_sessions"]:
        # If there is no column it's a plenary session
        if len(programme_session["program_sessions_program_columns"]) + len(programme_session["program_sessions_submissions"]) == 0:
            oa_programme_plenary.append(ProgrammeItem(
                date,
                programme_session["start_time"],
                programme_session["end_time"],
                programme_session["name"],
                "Plenary"))
        else:
            for programme_submission in programme_session["program_sessions_submissions"]:
                t = programme_session["program_sessions_program_columns"]
                track = t[0]["program_column"]["name"] if len(t) else "Plenary"
                oa_programme_submissions[programme_submission["submission_id"]].append(ProgrammeItem(
                    date,
                    programme_session["start_time"],
                    programme_session["end_time"],
                    programme_session["name"],
                    track))

#print("-----Programme Plenary Info-----")
#for a in oa_programme_plenary:
#  print(a)

#print("-----Programme Submission Info-----")
#for a,b in oa_programme_submissions.items():
#  for t in b:
#    print("%s: %s"%(a, t))

class Author:
  first=""
  last=""
  orcid=None
  institutions=[]
  
def accepted_for_to_upload_type(af):
    if af=="Poster & Lightning Talk":
        return "poster"
    elif af=="Talk" or af=="Walkthrough":
        return "presentation"
    if af=="Workshop":
        return "lesson"
    else: # Hackathon, Birds of a Feather
        return "other"

ZENODO_API = "https://sandbox.zenodo.org/" if conf.getboolean('ZENODO', 'use_sandbox') else "https://zenodo.org/"
# Setup the target Zenodo communities in the correct format
ZENODO_COMMUNITIES = []
for comm in conf.get('ZENODO', 'community_identifiers').split():
    ZENODO_COMMUNITIES.append({"identifier":comm})
ZENODO_KEYWORDS = conf.get('ZENODO', 'keywords').split()

skipped_sessions = set()

# Create output file to log progress of records
with open('oa2zenodo_log.csv', 'w', newline='') as logfile:
    log = csv.writer(logfile, dialect='excel')
    # Write header
    log.writerow(['submission_id', 'submission_title', 'zenodo_id', 'doi', 'status'])    
    # Process submissions
    for submission in oa_submissions:
        zenodo_id = ''
        zenodo_doi = ''
        sub_id = submission["id"]
        sub_title = submission["title"][0]["without_html"]
        sub_abstract = "" # Zenodo permits HTML
        sub_approve_upload = False
        sub_authors = []
        sub_type = accepted_for_to_upload_type(submission["accepted_for"]["value"])
        sub_has_permission = False
        sub_conference_session = None
        # Locate session info
        if sub_id in oa_programme_submissions:
            if len(oa_programme_submissions[sub_id])==1:
                sub_conference_session = oa_programme_submissions[sub_id][0].session_name
            else:
                # Submission is attached to multiple sessions, use input to offer user to select which is preferred
                # @todo, allow selection of multiple/all
                # Build menu
                menu_txt = f"The submission '{sub_title}' is attached to multiple sessions, please select which to use:\n"
                for i in range(len(oa_programme_submissions[sub_id])):
                    menu_txt += f"{i+1}: '{oa_programme_submissions[sub_id][i].session_name}'\n"
                menu_txt += f"{0}: Skip this submission\n"
                response = None
                while not response:
                  try:
                      response = int(input(menu_txt))
                  except ValueError:
                      print(f"An response in the inclusive range [0-{len(oa_programme_submissions[sub_id])}] required.")
                if response == 0:
                    log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, f"Found in multiple sessions and skipped by user."])
                    continue
                sub_conference_session = oa_programme_submissions[sub_id][response-1].session_name
                for i in range(len(oa_programme_submissions[sub_id])):
                    if i != response-1:
                        skipped_sessions.add(oa_programme_submissions[sub_id][i])
                 
            
        # Locate responses (abstract, upload_approval)
        for response in submission["responses"]:
            # abstract
            if response["question"]["question_name"] == "Abstract":
                sub_abstract = response["value"]
            # permission to publish
            elif response["question"]["question_name"] == "Permission to Publish":
                if response["value"] == "yes":
                    sub_has_permission = True
        if not sub_has_permission:
            log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, f"Permission to publish denied."])
            continue
                    
        # Extract author detail
        for author in submission["authors"]:
            a = dict()
            a["type"] = "ProjectMember" # Required field with controlled vocab, which we aren't collecting
            a["name"] = f"{author['last_name']}, {author['first_name']}"
            affiliations = ""
            for i in range(len(author["affiliations"])):
                if i != 0:
                    affiliations += ", "
                affiliations += author["affiliations"][i]["institution"]
            if affiliations:
                a["affiliation"] = author["orcid_id"]
            if author["orcid_id"]:
                a["orcid"] = author["orcid_id"]
            sub_authors.append(a)
        # Create Zenodo draft record  
        try:
            # https://developers.zenodo.org/#representation
            data = {  
              "metadata":{
                "upload_type": sub_type,
                "title": sub_title,
                "creators": sub_authors,
                "description": sub_abstract,
                "access_right": "open",
                "license": "cc-by",
                "keywords": ZENODO_KEYWORDS,
                "communities": ZENODO_COMMUNITIES,
                "conference_title": conf.get('ZENODO', 'conference_title'),
                "conference_acronym": conf.get('ZENODO', 'conference_acronym'),
                "conference_dates": conf.get('ZENODO', 'conference_dates'),
                "conference_place": conf.get('ZENODO', 'conference_place'),
                "conference_url": conf.get('ZENODO', 'conference_url'),
                "conference_session": sub_conference_session,
                #"conference_session_part": "", # @todo In future, 2024 no (standard) session has multiple parts
                #"grants": [{"id":"10.13039/501100000780::283595"}],# I don't think we are currently collecting this info
                "version": "1.0.0",
                "language": "eng",
                #"notes": ""# In future can add youtube link to notes
              }
            }
            r = requests.post(ZENODO_API+"api/deposit/depositions",
                params={'access_token': conf.get('ZENODO', 'api_key')},
                json=data)
            # Check/Response
            response = r.json()
            if r.status_code != 201:
              log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, f"Zenodo draft creation returned error: {response['message']}"])
              continue
            zenodo_id = response["id"]
            zenodo_doi = response["metadata"]["prereserve_doi"]["doi"]
        except Exception as e:
            # Update log
            log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, f"Zenodo draft creation failed: {e.message()}"])
            continue
        
        # User input to locate files
          
        # Upload and attach files to Zenodo record
        try:
              pass
        except Exception as e:
            # Update log
            log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, f"Uploading files to Zenodo failed: {e.message()}"])
            continue
            
        # Publish the draft record
        if not conf.getboolean('ZENODO', 'draft_only'):
            try:
                r = requests.post(ZENODO_API+f"api/deposit/depositions/{zenodo_id}/actions/publish",
                    params={'access_token': conf.get('ZENODO', 'api_key')})
                response = r.json()
                if r.status_code != 201:
                    log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, f"Publication of Zenodo draft returned error: {response['message']}"])
                    continue
            except Exception as e:
                # Update log
                log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, f"Publication of Zenodo draft failed: {e.message()}"])
                continue
        # Update log
        if conf.getboolean('ZENODO', 'draft_only'):
            log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, "Zenodo draft record created"])
        else:
            log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, "Zenodo record created and published"])
