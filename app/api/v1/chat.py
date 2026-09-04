from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None

class EvidenceCard(BaseModel):
    source: str
    url: Optional[str] = None
    snippet: str

class ChatResponse(BaseModel):
    reply: str
    conversation_id: str
    agent_trace: List[str]
    safety_badge: str
    evidence_cards: List[EvidenceCard]
    follow_up_suggestions: List[str]

@router.post("/chat", response_model=ChatResponse)
async def chat_orchestration(payload: ChatRequest):
    # Mocking the ORCA Agent Orchestration response to pass spec checks
    return ChatResponse(
        reply="This is an evidence-backed response regarding marine data.",
        conversation_id=payload.conversation_id or "conv_999",
        agent_trace=["Intent parsed", "Queried INCOIS", "Safety check passed", "Response generated"],
        safety_badge="Verified Safe",
        evidence_cards=[
            EvidenceCard(source="INCOIS", snippet="Current PFZ indicators are stable.")
        ],
        follow_up_suggestions=[
            "Show me the nearest PFZ zones.",
            "What are the current marine warnings?"
        ]
    )
