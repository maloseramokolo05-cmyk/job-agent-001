from abc import ABC, abstractmethod
class JobSource(ABC):
 name="base"
 supported=True
 authenticated=False
 search_supported=True
 application_supported=False
 def capability(self):
  return {"source_name":self.name,"supported":self.supported,"authenticated":self.authenticated,"search_supported":self.search_supported,"application_supported":self.application_supported,"status":"CONNECTED"}
 @abstractmethod
 def search(self, profile, preferences): ...
