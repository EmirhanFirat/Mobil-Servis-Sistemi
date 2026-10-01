// API sözleşmesinin (services/api/app/schemas.py) istemci tarafı karşılığı.

export type Role = 'requester' | 'technician' | 'admin';
export type TicketStatus =
  | 'new'
  | 'needs_review'
  | 'assigned'
  | 'in_progress'
  | 'resolved'
  | 'closed';
export type Priority = 'low' | 'normal' | 'high';
export type Category = 'electrical' | 'plumbing' | 'it_network' | 'cleaning' | 'other';

export interface Team {
  id: string;
  code: string;
  name: string;
}

export interface Person {
  id: string;
  display_name: string;
  role: Role;
}

export interface User {
  id: string;
  username: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  teams: Team[];
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface LabeledValue {
  code: string;
  label: string;
}

export interface Vocabulary {
  roles: LabeledValue[];
  statuses: LabeledValue[];
  priorities: LabeledValue[];
  categories: LabeledValue[];
  teams: LabeledValue[];
  missing_info: LabeledValue[];
  category_default_team: Record<string, string>;
}

export interface TicketSummary {
  id: string;
  number: number;
  title: string;
  location: string;
  status: TicketStatus;
  category: Category | null;
  priority: Priority;
  team: Team | null;
  assignee: Person | null;
  created_by: Person;
  missing_info: string[];
  review_required: boolean;
  created_at: string;
  updated_at: string;
}

export interface TicketEvent {
  id: number;
  kind: string;
  data: Record<string, unknown>;
  created_at: string;
  actor: Person | null;
}

export interface TicketDetail extends TicketSummary {
  description: string;
  allowed_transitions: TicketStatus[];
  can_assign: boolean;
  can_edit: boolean;
  events: TicketEvent[];
}

export interface TicketList {
  items: TicketSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface NewTicket {
  title: string;
  description: string;
  location: string;
}

export interface ListParams {
  scope?: 'mine' | 'queue';
  status?: TicketStatus[];
  limit?: number;
  offset?: number;
}
