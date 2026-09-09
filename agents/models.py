from dataclasses import asdict, dataclass, field


@dataclass
class Job:
    title: str
    company: str
    location: str
    source: str
    vacancy_url: str
    description: str = ""
    requirements: str = ""
    application_url: str = ""
    vacancy_id: str | None = None
    salary: str = ""
    date_posted: str | None = None
    closing_date: str | None = None
    work_mode: str = ""
    application_email: str = ""
    application_method: str = "WEB"
    email_verified: bool = False
    email_source_url: str = ""
    verified_at: str | None = None
    metadata: dict = field(default_factory=dict)

    def dict(self):
        return asdict(self)
