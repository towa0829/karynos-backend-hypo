from pydantic import BaseModel
from typing import List, Optional

class CreateDreamerRequest(BaseModel):
    name_family: str
    name_given: str

class CreateDreamerResponse(BaseModel):
    dreamer_id: str

class QuestionOption(BaseModel):
    option_id: str
    option_text: str

class Question(BaseModel):
    question_id: str
    question_text: str
    category: str
    options: List[QuestionOption]

class QuestionsResponse(BaseModel):
    questions: List[Question]

class AnswerItem(BaseModel):
    question_id: str
    option_id: str

class AnalyzeRequest(BaseModel):
    dreamer_id: str
    answers: List[AnswerItem]

class Recommendation(BaseModel):
    job_id: int
    history_id: str
    name: str
    salary: int
    age: int
    imgs: List[str]
    description: str
    similarity_score: float

class RecommendResponse(BaseModel):
    recommendation: Recommendation
