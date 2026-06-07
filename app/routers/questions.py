from fastapi import APIRouter
from schemas import QuestionsResponse, Question, QuestionOption
from questions_data import QUESTIONS

router = APIRouter(prefix="/api/v1/questions", tags=["questions"])


@router.get("", response_model=QuestionsResponse)
def get_questions():
    questions = []
    order = 1
    for cat in QUESTIONS:
        for q_item in cat["questions"]:
            qid = f"q{order}"
            options = [
                QuestionOption(
                    option_id=f"{qid}_o{i + 1}",
                    option_text=opt,
                )
                for i, opt in enumerate(q_item["opts"])
            ]
            questions.append(
                Question(
                    question_id=qid,
                    question_text=q_item["q"],
                    category=cat["category"],
                    options=options,
                )
            )
            order += 1
    return QuestionsResponse(questions=questions)
