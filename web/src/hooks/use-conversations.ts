import { useCallback } from "react";
import { useLiveQuery } from "dexie-react-hooks";
import { db, type ConversationRecord, type MessageRecord } from "@/db";

export function useConversations(project?: string) {
  const conversations = useLiveQuery(
    () =>
      project
        ? db.conversations.where("project").equals(project).reverse().sortBy("updatedAt")
        : db.conversations.orderBy("updatedAt").reverse().toArray(),
    [project],
  );

  const createConversation = useCallback(
    async (title: string, proj: string) => {
      const id = `conv_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
      const now = Date.now();
      const record: ConversationRecord = {
        id,
        title,
        project: proj,
        sessionId: null,
        createdAt: now,
        updatedAt: now,
      };
      await db.conversations.add(record);
      return record;
    },
    [],
  );

  const updateConversation = useCallback(
    async (id: string, updates: Partial<ConversationRecord>) => {
      await db.conversations.update(id, { ...updates, updatedAt: Date.now() });
    },
    [],
  );

  const deleteConversation = useCallback(async (id: string) => {
    await db.transaction("rw", [db.conversations, db.messages], async () => {
      await db.messages.where("conversationId").equals(id).delete();
      await db.conversations.delete(id);
    });
  }, []);

  return { conversations: conversations ?? [], createConversation, updateConversation, deleteConversation };
}

export function useMessages(conversationId: string | null) {
  const messages = useLiveQuery(
    () =>
      conversationId
        ? db.messages.where("conversationId").equals(conversationId).sortBy("createdAt")
        : Promise.resolve([] as MessageRecord[]),
    [conversationId],
  );

  const addMessage = useCallback(
    async (msg: Omit<MessageRecord, "id">) => {
      const id = `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
      await db.messages.add({ ...msg, id });
      // Update conversation timestamp
      await db.conversations.update(msg.conversationId, { updatedAt: Date.now() });
      return id;
    },
    [],
  );

  return { messages: messages ?? [], addMessage };
}
