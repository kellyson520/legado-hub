import json

from sqlalchemy import or_

from app.core.pagination import LIKE_ESCAPE, like_pattern
from app.infrastructure.persistence.sqlite.session import SessionLocal
from app.domain.entities.ai_conversation import AIConversation, AIConversationMessage
from app.domain.repositories.ai_conversation_repo import AIConversationRepository

from .schema import AIConversationMessageModel, AIConversationModel


class SQLiteAIConversationRepository(AIConversationRepository):
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db) -> None:
        if self._session is None:
            db.close()

    def create_conversation(self, conversation: AIConversation) -> AIConversation:
        db = self._db()
        try:
            model = AIConversationModel(
                id=conversation.id,
                actor_id=conversation.actor_id,
                owner_scope=conversation.owner_scope,
                title=conversation.title,
                book_id=conversation.book_id,
                chapter_id=conversation.chapter_id,
                entrypoint=conversation.entrypoint,
                context_range=conversation.context_range,
                model_ref=conversation.model_ref,
                knowledge_version=conversation.knowledge_version,
                toolset_version=conversation.toolset_version,
                created_at=conversation.created_at,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._conversation(model)
        finally:
            self._close(db)

    def list_conversations(self, actor_id: str, owner_scope: str | None = None) -> list[AIConversation]:
        db = self._db()
        try:
            query = db.query(AIConversationModel).filter(AIConversationModel.actor_id == actor_id)
            if owner_scope is not None:
                query = query.filter(AIConversationModel.owner_scope == owner_scope)
            rows = query.order_by(AIConversationModel.created_at.desc()).all()
            return [self._conversation(row) for row in rows]
        finally:
            self._close(db)

    def list_conversations_page(
        self,
        actor_id: str,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        owner_scope: str | None = None,
    ) -> tuple[list[AIConversation], int]:
        db = self._db()
        try:
            query = db.query(AIConversationModel).filter(AIConversationModel.actor_id == actor_id)
            if owner_scope is not None:
                query = query.filter(AIConversationModel.owner_scope == owner_scope)
            normalized_search = search.strip()
            if normalized_search:
                pattern = like_pattern(normalized_search)
                query = query.filter(
                    or_(
                        AIConversationModel.id.ilike(pattern, escape=LIKE_ESCAPE),
                        AIConversationModel.title.ilike(pattern, escape=LIKE_ESCAPE),
                    )
                )
            total = query.count()
            rows = (
                query.order_by(AIConversationModel.created_at.desc(), AIConversationModel.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            return [self._conversation(row) for row in rows], total
        finally:
            self._close(db)

    def get_conversation(self, conversation_id: str, actor_id: str, owner_scope: str | None = None) -> AIConversation | None:
        db = self._db()
        try:
            query = db.query(AIConversationModel).filter(
                AIConversationModel.id == conversation_id,
                AIConversationModel.actor_id == actor_id,
            )
            if owner_scope is not None:
                query = query.filter(AIConversationModel.owner_scope == owner_scope)
            model = query.first()
            return self._conversation(model) if model is not None else None
        finally:
            self._close(db)

    def append_message(self, message: AIConversationMessage) -> AIConversationMessage:
        db = self._db()
        try:
            model = AIConversationMessageModel(
                id=message.id,
                conversation_id=message.conversation_id,
                role=message.role,
                mode=message.mode,
                content=message.content,
                status=message.status,
                tool_calls=json.dumps(message.tool_calls, ensure_ascii=False),
                metadata_payload=json.dumps(message.metadata, ensure_ascii=False),
                owner_scope=message.owner_scope,
                entrypoint=message.entrypoint,
                book_id=message.book_id,
                chapter_id=message.chapter_id,
                created_at=message.created_at,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._message(model)
        finally:
            self._close(db)

    def list_messages(self, conversation_id: str, owner_scope: str | None = None) -> list[AIConversationMessage]:
        db = self._db()
        try:
            query = db.query(AIConversationMessageModel).filter(AIConversationMessageModel.conversation_id == conversation_id)
            if owner_scope is not None:
                query = query.filter(AIConversationMessageModel.owner_scope == owner_scope)
            rows = query.order_by(AIConversationMessageModel.created_at.asc()).all()
            return [self._message(row) for row in rows]
        finally:
            self._close(db)

    def list_recent_messages(
        self,
        conversation_id: str,
        owner_scope: str | None = None,
        limit: int = 12,
    ) -> list[AIConversationMessage]:
        db = self._db()
        try:
            query = db.query(AIConversationMessageModel).filter(
                AIConversationMessageModel.conversation_id == conversation_id
            )
            if owner_scope is not None:
                query = query.filter(AIConversationMessageModel.owner_scope == owner_scope)
            rows = (
                query.order_by(
                    AIConversationMessageModel.created_at.desc(),
                    AIConversationMessageModel.id.desc(),
                )
                .limit(max(1, min(int(limit), 100)))
                .all()
            )
            rows.reverse()
            return [self._message(row) for row in rows]
        finally:
            self._close(db)

    @staticmethod
    def _conversation(model: AIConversationModel) -> AIConversation:
        return AIConversation(
            id=model.id,
            actor_id=model.actor_id,
            title=model.title,
            owner_scope=model.owner_scope,
            book_id=model.book_id,
            chapter_id=model.chapter_id,
            entrypoint=model.entrypoint,
            context_range=model.context_range,
            model_ref=model.model_ref,
            knowledge_version=model.knowledge_version,
            toolset_version=model.toolset_version,
            created_at=model.created_at,
        )

    @staticmethod
    def _message(model: AIConversationMessageModel) -> AIConversationMessage:
        return AIConversationMessage(
            id=model.id,
            conversation_id=model.conversation_id,
            role=model.role,
            mode=model.mode,
            content=model.content,
            status=model.status,
            tool_calls=json.loads(model.tool_calls or "[]"),
            metadata=json.loads(model.metadata_payload or "{}"),
            owner_scope=model.owner_scope,
            entrypoint=model.entrypoint,
            book_id=model.book_id,
            chapter_id=model.chapter_id,
            created_at=model.created_at,
        )
