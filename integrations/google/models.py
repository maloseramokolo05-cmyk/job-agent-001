from dataclasses import dataclass
GMAIL_READONLY="https://www.googleapis.com/auth/gmail.readonly"
GMAIL_COMPOSE="https://www.googleapis.com/auth/gmail.compose"
GMAIL_SEND="https://www.googleapis.com/auth/gmail.send"
DRIVE_FILE="https://www.googleapis.com/auth/drive.file"
CALENDAR_EVENTS="https://www.googleapis.com/auth/calendar.events"
FEATURE_SCOPES={"gmail":[GMAIL_READONLY,GMAIL_COMPOSE],"gmail_send":[GMAIL_SEND],"drive":[DRIVE_FILE],"calendar":[CALENDAR_EVENTS]}
@dataclass
class IntegrationState:
 connected:bool; status:str; scopes:list[str]; last_sync:str|None=None
