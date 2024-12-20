import requests, sys, configparser, csv, os, random, re
from collections import defaultdict
from fnmatch import fnmatch

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
    submissions(
      where: {decision: {value: {_eq: "Accepted"}}, archived: {_eq: false}}
    ) {
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
      serial_number
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

# Locate fake file if requested
fake_file_path = ""
if conf.getboolean('ZENODO', 'fake_upload') and conf.getboolean('ZENODO', 'use_sandbox'):
    fake_file = None
    while not fake_file:
        fake_file_path = input("Specify location of fake file to use for Sandbox uploads: ")
        fake_file = open(fake_file_path, 'rb')
    del fake_file
elif conf.getboolean('ZENODO', 'fake_upload'):
    print("Error: fake_upload=TRUE is not compatible with use_sandbox=FALSE.")
    sys.exit()

# Process skipped submissions into a set of integers
SKIPPED_SUBMISSIONS = set()
if 'skipped_submissions' in conf['ZENODO']:
    SKIPPED_SUBMISSIONS = set([int(i) for i in conf['ZENODO']['skipped_submissions'].split()])

# Build a map of id:upload-folder-path (because GLOB sucks)
UPLOAD_DIRS = {}
for root, dirs, files in os.walk(conf['ZENODO']['file_search_root']):
    for dir in dirs:
        m = re.search("^ID ?([0-9]+)",dir)
        if m:
            if int(m.group(1)) in UPLOAD_DIRS:
                raise Exception(f"2 dirs for submission {m.group(1)}\n{UPLOAD_DIRS[int(m.group(1))]}\n{os.path.join(root, dir)}")
            UPLOAD_DIRS[int(m.group(1))] = os.path.join(root, dir)

# Build a map of id:youtube-url
YOUTUBE_URLS = {}
if "youtube_csv" in conf['ZENODO']:
    if not ("youtube_csv_id" in conf['ZENODO'] and "youtube_csv_url" in  conf['ZENODO']):
        raise Exception("Input contains 'youtube_csv', but not both 'youtube_csv_id' and 'youtube_csv_url' which denote column headings")
    with open(conf['ZENODO']['youtube_csv'], mode='r', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        key = conf['ZENODO']['youtube_csv_id']
        val = conf['ZENODO']['youtube_csv_url']
        for row in reader:
            # Only use rows that have data
            if len(row[key]) and len(row[val]):
                try:
                    # Regular 1:1 matches
                    YOUTUBE_URLS[int(row[key])] = row[val]
                except ValueError:
                    i = row[key].split(",")
                    for j in i:
                        # N:1 matches (Poster lighting talks)
                        YOUTUBE_URLS[int(j)] = row[val]

FILE_BLACKLIST = conf['ZENODO']['file_blacklist'].split() if 'file_blacklist' in conf['ZENODO'] else []

# Create output file to log progress of records
with open('oa2zenodo_log.csv', 'w', newline='') as logfile:
    log = csv.writer(logfile, dialect='excel')
    # Write header
    log.writerow(['submission_id', 'submission_title', 'zenodo_id', 'doi', 'status'])    
    # Process submissions
    for submission in oa_submissions:
        zenodo_id = ''
        zenodo_doi = ''
        sub_global_id = submission["id"] # This is a globally unique ID
        sub_id = submission["serial_number"] # This is ID from within OA website
        sub_title = submission["title"][0]["without_html"]
        sub_abstract = "" # Zenodo permits HTML
        sub_approve_upload = False
        sub_authors = []
        sub_type = accepted_for_to_upload_type(submission["accepted_for"]["value"])
        sub_has_permission = False
        sub_conference_session = None
        if sub_id in SKIPPED_SUBMISSIONS:
            log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, f"Skipped as requested by config"])
            continue
        # Locate session info
        if sub_global_id in oa_programme_submissions:
            # Filter out duplicate and previously skipped session names
            matching_sessions = []
            for x in oa_programme_submissions[sub_global_id]:
                if (x.session_name not in matching_sessions
                and x.session_name not in skipped_sessions):
                    matching_sessions.append(x.session_name)
            # Perform selection
            if len(matching_sessions)==0:
                log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, f"Found only in previously skipped sessions, so ignored."])
                continue
            elif len(matching_sessions)==1:
                sub_conference_session = matching_sessions[0]
            else:
                # Submission is attached to multiple sessions, use input to offer user to select which is preferred
                # @todo, allow selection of multiple/all?
                # Build menu
                menu_txt = f"The submission '{sub_title}' is attached to multiple sessions, please select which to use:\n"
                for i in range(len(matching_sessions)):
                    menu_txt += f"{i+1}: '{matching_sessions[i]}'\n"
                menu_txt += f"{0}: Skip this submission\n"
                response = None
                while not response:
                  try:
                      response = int(input(menu_txt))
                  except ValueError:
                      print(f"An response in the inclusive range [0-{len(matching_sessions)}] required.")
                if response == 0:
                    log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, f"Found in multiple sessions and skipped by user."])
                    continue
                sub_conference_session = matching_sessions[response-1]
                for i in range(len(matching_sessions)):
                    if i != response-1:
                        skipped_sessions.add(matching_sessions[i])
                 
            
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

        # Append YouTube URL if available
        if sub_id in YOUTUBE_URLS:
            sub_abstract += f"\nA recording of this session is available on YouTube: <a href=\"{YOUTUBE_URLS[sub_id]}\">{YOUTUBE_URLS[sub_id]}</a>"

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
        if not conf.getboolean('ZENODO', 'dry_run'):
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
                if r.status_code // 100 != 2:
                    log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, f"Zenodo draft creation returned error: {response['message']}"])
                    continue
                zenodo_id = response["id"]
                zenodo_doi = response["metadata"]["prereserve_doi"]["doi"]
            except Exception as e:
                # Update log
                log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, f"Zenodo draft creation failed: {e.message()}"])
                continue
        else:
            # Fake dry run data
            zenodo_id = random.randint(1, 100000000)
            zenodo_doi = random.randint(1, 100000000)
            print(f"[DRY] Created Zenodo record for submission #{sub_id}")  
        
        # Create a list for this submissions files
        sub_files = []
        if conf.getboolean('ZENODO', 'fake_upload'):
            sub_files.append(fake_file_path)
        else:
          # @todo User input to confirm files
          # Locate the folder corresponding to the file's ID
          if not sub_id in UPLOAD_DIRS:
              # The cloudkubed sponsor workshop (#174) doesn't have a google drive directory
                log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, f"Google drive directory missing"])
                continue
          sub_folder = UPLOAD_DIRS[sub_id]
          # Check whether there is a "zenodo" directory (case-insensitive)
          for f in os.listdir(sub_folder):
              t_sub_folder = os.path.join(sub_folder, f)
              if os.path.isdir(t_sub_folder) and f.lower() == "zenodo":
                  sub_folder = t_sub_folder
                  break
          # Locate all files to be uploaded
          sub_files = []
          for root, _, files in os.walk(sub_folder):
              for file in files:
                  skip = False
                  for test_filename in FILE_BLACKLIST:
                      if fnmatch(file.lower(), test_filename.lower()):
                          skip = True
                          break
                  if not skip:
                    sub_files.append(os.path.join(root, file))
        # Upload and attach files to Zenodo record
        for sf in sub_files:
            # @todo Filter out certain files (e.g. transcripts, google slides, desktop.ini)                
            if not conf.getboolean('ZENODO', 'dry_run'):
                try:
                    sf_name = os.path.basename(sf)
                    sf_file = open(sf, 'rb')
                    r = requests.post(ZENODO_API+f"api/deposit/depositions/{zenodo_id}/files",
                        params={'access_token': conf.get('ZENODO', 'api_key')},
                        data={"name": sf_name},
                        files={'file': sf_file})
                    response = r.json()
                    if r.status_code // 100 != 2:
                        log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, f"File upload '{sf_name}' to Zenodo returned error: {response['message']}"])
                        continue
                except OSError as e:
                    # Update log
                    log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, f"Failed to open file '{sf}': {e.strerror}"])
                except Exception as e:
                    # Update log
                    log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, f"Uploading file '{sf_name}' to Zenodo failed: {e.message()}"])
                    continue
            else:
                print(f"[DRY] Uploaded '{sf}' for submission #{sub_id}")
            
        # Publish the draft record
        if not conf.getboolean('ZENODO', 'draft_only'):
            if not conf.getboolean('ZENODO', 'dry_run'):
                try:
                    r = requests.post(ZENODO_API+f"api/deposit/depositions/{zenodo_id}/actions/publish",
                        params={'access_token': conf.get('ZENODO', 'api_key')})
                    response = r.json()
                    if r.status_code // 100 != 2:
                        log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, f"Publication of Zenodo draft returned error: {response['message']}"])
                        continue
                except Exception as e:
                    # Update log
                    log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, f"Publication of Zenodo draft failed: {e.message()}"])
                    continue
            else:
                print(f"[DRY] Published submission #{sub_id}")
        # Update log
        if conf.getboolean('ZENODO', 'draft_only'):
            log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, "Zenodo draft record created"])
        else:
            log.writerow([sub_id, sub_title, zenodo_id, zenodo_doi, "Zenodo record created and published"])
