import enum


class Seniority(str, enum.Enum):
    junior = "junior"
    mid = "mid"
    senior = "senior"


class PreferredLanguage(str, enum.Enum):
    ca = "ca"
    es = "es"
    en = "en"


class ApplicationStatus(str, enum.Enum):
    saved = "saved"
    applied = "applied"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"
    withdrawn = "withdrawn"


class EventType(str, enum.Enum):
    interview = "interview"
    follow_up = "follow_up"
    note = "note"
    status_change = "status_change"


class MatchStatus(str, enum.Enum):
    new = "new"
    dismissed = "dismissed"
    converted = "converted"
