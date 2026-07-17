"""
AI Agents for RoleMule.

Workflow Agents (LangGraph):
- job_analyzer: Extracts requirements from job postings
- profile_matching: Evaluates user-job fit
- company_research: Gathers company intelligence
- resume_advisor: Generates resume recommendations
- cover_letter_writer: Creates personalized cover letters

Career Tools (Standalone):
- thank_you_writer: Post-interview thank you notes
- rejection_analyzer: Rejection email analysis
- reference_request_writer: Reference request emails
- job_comparison: Side-by-side job comparison
- followup_generator: Follow-up emails
- salary_coach: Salary negotiation coaching

Standalone Agent:
- interview_prep: Interview preparation materials
"""

from .job_analyzer import JobAnalyzerAgent
from .profile_matching import ProfileMatchingAgent
from .company_research import CompanyResearchAgent
from .resume_advisor import ResumeAdvisorAgent
from .cover_letter_writer import CoverLetterWriterAgent
from .interview_prep import InterviewPrepAgent
from .thank_you_writer import ThankYouWriterAgent
from .rejection_analyzer import RejectionAnalyzerAgent
from .reference_request_writer import ReferenceRequestWriterAgent
from .job_comparison import JobComparisonAgent
from .followup_generator import FollowUpGeneratorAgent
from .salary_coach import SalaryCoachAgent

__all__ = [
    # Workflow agents
    "JobAnalyzerAgent",
    "ProfileMatchingAgent",
    "CompanyResearchAgent",
    "ResumeAdvisorAgent",
    "CoverLetterWriterAgent",
    # Standalone agent
    "InterviewPrepAgent",
    # Career tools
    "ThankYouWriterAgent",
    "RejectionAnalyzerAgent",
    "ReferenceRequestWriterAgent",
    "JobComparisonAgent",
    "FollowUpGeneratorAgent",
    "SalaryCoachAgent",
]
