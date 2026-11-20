ROLES = ("candidate", "employer", "recruiter", "admin")
WORK_MODES = ("remote", "onsite", "hybrid")
EMPLOYMENT_TYPES = ("full_time", "part_time", "contract", "internship", "freelance", "temporary")
EXPERIENCE_LEVELS = ("Entry Level", "Junior", "Mid Level", "Senior", "Lead", "Executive")
LEVEL_YEARS = {"Entry Level": (0, 1), "Junior": (1, 3), "Mid Level": (3, 5), "Senior": (5, 8), "Lead": (8, 12), "Executive": (12, 40)}
JOB_STATUSES = ("active", "closed", "expired", "pending_review", "removed")
APPLICATION_STATUSES = ("submitted", "viewed", "under_review", "shortlisted", "interview_scheduled", "offer", "rejected", "withdrawn")
EMPLOYER_TRANSITIONS = {
    "submitted": {"viewed", "under_review", "shortlisted", "rejected"},
    "viewed": {"under_review", "shortlisted", "rejected"},
    "under_review": {"shortlisted", "interview_scheduled", "rejected"},
    "shortlisted": {"under_review", "interview_scheduled", "offer", "rejected"},
    "interview_scheduled": {"shortlisted", "offer", "rejected"},
    "offer": {"rejected"},
    "rejected": set(),
    "withdrawn": set(),
}
CANDIDATE_WITHDRAWABLE = {"submitted", "viewed", "under_review", "shortlisted", "interview_scheduled"}
EDUCATION_LEVELS = {"none": 0, "high_school": 1, "diploma": 2, "bachelor": 3, "master": 4, "phd": 5}
DEFAULT_WEIGHTS = {"skills": 0.45, "experience": 0.20, "education": 0.10, "location": 0.10, "semantic": 0.10, "preferences": 0.05}
DEFAULT_CATEGORIES = [
    "Software Development", "Data & AI", "DevOps & Infrastructure", "Design", "Product", "Marketing",
    "Sales", "Customer Support", "Finance", "Human Resources", "Operations", "Writing & Content",
    "Healthcare", "Education", "Other",
]
