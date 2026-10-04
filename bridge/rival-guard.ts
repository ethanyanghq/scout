// Stops scout from answering twice when two people run the bridge at once.
//
// Teammates share one Linq key, so each Mac's `linq webhooks listen` receives
// every message and each bridge would reply. Before sending, a bridge checks
// the chat for a message from scout's number that it didn't send itself. If
// one arrived since the member last spoke, another bridge got there first, and
// this one stays quiet. Two bridges sending in the same instant can still
// both get through; Claude's replies take seconds, so that is rare.

import { callLinq, type LinqApi } from "./linq-api";

// A page of the newest messages is plenty: the rival's reply is among them.
const MESSAGES_TO_CHECK = 20;

export class AnotherScoutAnsweredError extends Error {
  constructor(chatId: string) {
    super(`another scout bridge already answered in chat ${chatId}`);
  }
}

type ListedMessage = { id: string; is_from_me: boolean; created_at: string };

export class RivalGuard {
  private readonly ownMessageIds = new Set<string>();
  private readonly lastMemberMessageAt = new Map<string, Date>();

  noteMemberMessage(chatId: string, sentAt: Date): void {
    this.lastMemberMessageAt.set(chatId, sentAt);
  }

  noteOwnMessage(messageId: string): void {
    this.ownMessageIds.add(messageId);
  }

  async assertNobodyElseAnswered(api: LinqApi, chatId: string): Promise<void> {
    const memberSpokeAt = this.lastMemberMessageAt.get(chatId);
    if (!memberSpokeAt) return;
    const { messages } = (await callLinq(
      api,
      `/chats/${chatId}/messages?limit=${MESSAGES_TO_CHECK}`,
    )) as { messages: ListedMessage[] };
    const rivalReply = messages.find(
      (message) =>
        message.is_from_me &&
        !this.ownMessageIds.has(message.id) &&
        new Date(message.created_at) >= memberSpokeAt,
    );
    if (rivalReply) throw new AnotherScoutAnsweredError(chatId);
  }
}
