/** Mirrors apps/api/app/schemas.py. Keep the two in step. */

export type BusinessHoursWindow = { open: string; close: string };
export type BusinessHours = Record<string, BusinessHoursWindow[]>;

export type ServiceItem = { name: string; duration_minutes: number };

export type Business = {
  id: string;
  name: string;
  timezone: string;
  greeting: string;
  business_hours: BusinessHours;
  services: ServiceItem[];
};

export type PublicBusiness = {
  id: string;
  name: string;
  greeting: string;
  timezone: string;
  services: ServiceItem[];
};

export type DocumentStatus = "pending" | "ready" | "failed";

export type VoxaDocument = {
  id: string;
  filename: string;
  mime_type: string;
  byte_size: number;
  status: DocumentStatus;
  error: string | null;
  created_at: string;
};

export type DocumentUploadResult = {
  document: VoxaDocument;
  chunks_indexed: number;
};

export type MessageRole = "customer" | "assistant";

export type Message = {
  id: string;
  role: MessageRole;
  content: string;
  intent: string | null;
  created_at: string;
};

export type ConversationOutcome =
  | "in_progress"
  | "booked"
  | "answered"
  | "escalated"
  | "abandoned";

export type Conversation = {
  id: string;
  channel: "voice" | "text";
  outcome: ConversationOutcome;
  customer_name: string | null;
  customer_email: string | null;
  started_at: string;
  ended_at: string | null;
};

export type ConversationDetail = Conversation & { messages: Message[] };

export type Booking = {
  id: string;
  customer_name: string;
  customer_email: string | null;
  customer_phone: string | null;
  service: string | null;
  starts_at: string;
  ends_at: string;
  status: "confirmed" | "rescheduled" | "cancelled";
  google_event_id: string | null;
  created_at: string;
};

export type FollowUpStatus = "open" | "resolved";

export type FollowUp = {
  id: string;
  conversation_id: string | null;
  question: string;
  customer_name: string | null;
  customer_email: string | null;
  customer_phone: string | null;
  status: FollowUpStatus;
  created_at: string;
  resolved_at: string | null;
};

export type GoogleStatus = {
  connected: boolean;
  calendar_id: string | null;
  google_account_email: string | null;
  connected_at: string | null;
  oauth_configured: boolean;
};

export type ChatResponse = {
  conversation_id: string;
  reply: string;
  intent: string;
  outcome: ConversationOutcome;
  sources: string[];
};
