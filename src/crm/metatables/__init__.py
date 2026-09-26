"""Explicit platform-managed CRM MetaTable declarations."""

from .activity_event import ActivityEvent
from .base import Base as Base
from .company import Company
from .contact import Contact
from .contact_company_affiliation import ContactCompanyAffiliation
from .contact_tag import ContactTag
from .deal import Deal
from .deal_contact import DealContact
from .entity_redirect import EntityRedirect
from .google_oauth import GoogleOAuthAttempt, GoogleOAuthConnection
from .interaction import Interaction
from .note import Note
from .pipeline import Pipeline
from .settings import Settings
from .solution_selling import (
    SolutionSelling,
    SolutionSellingDiagnosis,
    SolutionSellingLead,
    SolutionSellingPrompter,
    SolutionSellingProspectingProfile,
)
from .source_connection import SourceConnection
from .source_identity import SourceIdentity
from .stage import Stage
from .tag import Tag
from .task import Task
from .transfer_job import TransferJob
from .transfer_row import TransferRow

MODELS = {
    "settings": Settings,
    "pipeline": Pipeline,
    "stage": Stage,
    "company": Company,
    "contact": Contact,
    "contact_company_affiliation": ContactCompanyAffiliation,
    "tag": Tag,
    "contact_tag": ContactTag,
    "deal": Deal,
    "deal_contact": DealContact,
    "note": Note,
    "task": Task,
    "activity_event": ActivityEvent,
    "entity_redirect": EntityRedirect,
    "source_connection": SourceConnection,
    "source_identity": SourceIdentity,
    "transfer_job": TransferJob,
    "transfer_row": TransferRow,
    "interaction": Interaction,
    "google_oauth_attempt": GoogleOAuthAttempt,
    "google_oauth_connection": GoogleOAuthConnection,
    "solution_selling": SolutionSelling,
    "solution_selling_diagnosis": SolutionSellingDiagnosis,
    "solution_selling_prospecting_profile": SolutionSellingProspectingProfile,
    "solution_selling_lead": SolutionSellingLead,
    "solution_selling_prompter": SolutionSellingPrompter,
}
