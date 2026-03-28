import Dexie, { type EntityTable } from "dexie";

export interface ConversationRecord {
  id: string;
  title: string;
  project: string;
  sessionId: string | null;
  createdAt: number;
  updatedAt: number;
}

export interface MessageRecord {
  id: string;
  conversationId: string;
  role: "user" | "assistant";
  content: string;
  sources?: Array<{
    index: number;
    file: string;
    chunk: string;
    score: number;
    start_line?: number;
    end_line?: number;
  }>;
  agentSteps?: Array<{
    thought: string;
    action?: string;
    observation?: string;
    answer?: string;
  }>;
  createdAt: number;
}

class DelphiDB extends Dexie {
  conversations!: EntityTable<ConversationRecord, "id">;
  messages!: EntityTable<MessageRecord, "id">;

  constructor() {
    super("delphi");
    this.version(1).stores({
      conversations: "id, project, updatedAt",
      messages: "id, conversationId, createdAt",
    });
  }
}

export const db = new DelphiDB();
