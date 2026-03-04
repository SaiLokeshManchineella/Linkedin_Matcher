from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class AnalyzeRequest(BaseModel):
    linkedin_url: str = Field(..., description="LinkedIn profile URL")


class AnalyzeResponse(BaseModel):
    profile: Dict[str, Any]
    recent_posts: List[str]
    questions: List[str]
    reasoning: str
    returning_user: bool = False
    returning_full_name: str = ""          # populated only when returning_user=True
    cached_result: Optional[Dict[str, Any]] = None  # serialized SubmitAnswersResponse


class AnswerItem(BaseModel):
    question: str
    answer: str


class MatchedUser(BaseModel):
    fullName: str = ""
    headline: str = ""
    linkedin_url: str = ""
    profile_image_url: str = ""
    similarity: float = 0.0
    topics: List[str] = []
    reason: str = ""
    source: str = "qdrant"  # "qdrant" or "linkedin_search"


class SubmitAnswersRequest(BaseModel):
    linkedin_url: str
    answers: List[AnswerItem]


class SubmitAnswersResponse(BaseModel):
    user_topics: List[str]
    user_reasoning: str
    matched_users: List[MatchedUser]
    total_from_db: int
    total_from_graph: int = 0
    total_from_linkedin: int
