from .base import JobSource
from agents.models import Job
class SampleSource(JobSource):
 name="sample"
 def search(self,profile,preferences):
  return [Job("Marketing Coordinator","Example Employer","Pretoria, Gauteng",self.name,"https://example.com/jobs/marketing-coordinator",description="Coordinate digital marketing, social media, content and customer campaigns.",requirements="Communication, digital marketing, content creation",application_url="https://example.com/jobs/marketing-coordinator/apply",vacancy_id="sample-001",work_mode="Hybrid")]
