import os
from datetime import datetime
from pydantic import BaseModel, Field, computed_field


class WorkspaceBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=2, max_length=120)
    description: str | None = None


class WorkspaceCreate(WorkspaceBase):
    pass


class WorkspaceOut(WorkspaceBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    slug: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = None


class MemberBase(BaseModel):
    full_name: str
    email: str
    role: str = "member"
    level: str | None = None


class MemberCreate(MemberBase):
    pass


class MemberOut(MemberBase):
    id: int
    workspace_id: int
    dues_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RoleOut(BaseModel):
    id: int
    workspace_id: int
    key: str
    name: str
    description: str | None = None
    is_system_role: bool
    permissions: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = None
    permissions: list[str] = []


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = None
    permissions: list[str] | None = None


class UserOut(BaseModel):
    id: int
    full_name: str
    email: str
    phone: str | None = None
    email_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceMemberOut(BaseModel):
    id: int
    workspace_id: int
    user_id: int
    role_id: int
    full_name: str
    email: str
    role: str
    role_key: str
    level: str | None = None
    dues_status: str
    status: str
    is_general_member: bool
    created_at: datetime


class DuesCycleCreate(BaseModel):
    name: str
    amount: float
    deadline: str | None = None


class DuesCycleOut(DuesCycleCreate):
    id: int
    workspace_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class DuesPaymentCreate(BaseModel):
    member_id: int | None = None
    amount: float
    method: str = "manual"
    gateway_ref: str | None = None
    receipt_url: str | None = None


class DuesPaymentCheckoutCreate(BaseModel):
    member_id: int | None = None
    email: str | None = None
    amount: float | None = Field(default=None, gt=0)


class DuesPaymentOut(BaseModel):
    id: int
    workspace_id: int
    cycle_id: int
    member_id: int | None = None
    member_name: str | None = None
    amount: float
    method: str
    gateway_ref: str | None = None
    receipt_url: str | None = None
    status: str
    confirmed_by_user_id: int | None = None
    confirmed_at: datetime | None = None
    created_at: datetime


class DuesPaymentCheckoutResponse(BaseModel):
    payment: DuesPaymentOut
    payment_reference: str
    checkout_url: str | None = None
    access_code: str | None = None
    provider: str = "paystack"


class EventCreate(BaseModel):
    title: str
    slug: str
    event_type: str = "social"
    starts_at: str
    venue: str | None = None
    description: str | None = None
    rsvp_enabled: bool = True
    capacity: int | None = None
    thumbnail_url: str | None = None


class EventOut(EventCreate):
    id: int
    workspace_id: int
    rsvp_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class EventUpdate(BaseModel):
    title: str | None = None
    event_type: str | None = None
    starts_at: str | None = None
    venue: str | None = None
    description: str | None = None
    rsvp_enabled: bool | None = None
    capacity: int | None = None
    thumbnail_url: str | None = None


class EventAttendeeCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str


class EventAttendeeOut(BaseModel):
    id: int
    event_id: int
    workspace_id: int
    member_id: int | None = None
    full_name: str
    email: str
    status: str
    rsvp_at: datetime
    checked_in_at: datetime | None = None


class EventDetailOut(EventOut):
    attendees: list[EventAttendeeOut] = Field(default_factory=list)


class EventAnalyticsPoint(BaseModel):
    label: str
    value: int


class EventAnalyticsOut(BaseModel):
    total_events: int
    total_rsvps: int
    total_checked_in: int
    by_type: list[EventAnalyticsPoint]


class CampaignCreate(BaseModel):
    name: str
    slug: str
    target_amount: float


class CampaignOut(CampaignCreate):
    id: int
    workspace_id: int
    raised_amount: float
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FundingStreamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    stream_type: str = "general"
    target_amount: float | None = None


class FundingStreamOut(FundingStreamCreate):
    id: int
    workspace_id: int
    campaign_id: int
    raised_amount: float = 0
    created_at: datetime


class ContributionCreate(BaseModel):
    stream_id: int | None = None
    contributor_name: str | None = None
    contributor_email: str | None = None
    amount: float = Field(gt=0)
    method: str = "manual"
    gateway_ref: str | None = None
    receipt_url: str | None = None
    is_anonymous: bool = False


class ContributionOut(BaseModel):
    id: int
    workspace_id: int
    campaign_id: int
    stream_id: int | None = None
    stream_name: str | None = None
    contributor_name: str | None = None
    contributor_email: str | None = None
    amount: float
    method: str
    gateway_ref: str | None = None
    receipt_url: str | None = None
    is_anonymous: bool
    status: str
    confirmed_by_user_id: int | None = None
    confirmed_at: datetime | None = None
    created_at: datetime


class CampaignDetailOut(CampaignOut):
    funding_streams: list[FundingStreamOut] = Field(default_factory=list)
    contributions: list[ContributionOut] = Field(default_factory=list)
    contributor_count: int = 0


class PublicContributionCreate(BaseModel):
    stream_id: int | None = None
    contributor_name: str | None = None
    contributor_email: str | None = None
    amount: float = Field(gt=0)
    is_anonymous: bool = False


class PublicContributionResponse(BaseModel):
    contribution: ContributionOut
    payment_reference: str
    checkout_url: str | None = None
    access_code: str | None = None
    provider: str = "paystack"


class LinkCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=80)
    destination_url: str = Field(min_length=8, max_length=2000)
    title: str | None = Field(default=None, max_length=200)
    expires_at: datetime | None = None


class LinkUpdate(BaseModel):
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    destination_url: str | None = Field(default=None, min_length=8, max_length=2000)
    title: str | None = Field(default=None, max_length=200)
    expires_at: datetime | None = None
    is_active: bool | None = None


class LinkOut(LinkCreate):
    id: int
    workspace_id: int
    click_count: int
    is_active: bool
    created_at: datetime

    @computed_field
    @property
    def short_url(self) -> str:
        base_url = (
            os.getenv("APP_URL")
            or os.getenv("PUBLIC_APP_URL")
            or os.getenv("FRONTEND_URL")
            or "http://localhost:3000"
        )
        return f"{base_url.rstrip('/')}/{self.slug}"

    model_config = {"from_attributes": True}


class ClickRequest(BaseModel):
    link_id: int
    referer: str | None = None
    user_agent: str | None = None


class DailyClickCount(BaseModel):
    day: str
    count: int


class LinkAnalyticsOut(BaseModel):
    link_id: int
    total: int
    daily: list[DailyClickCount]


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    body: str = Field(min_length=2)
    status: str = "published"
    is_pinned: bool = False
    published_at: datetime | None = None
    scheduled_for: datetime | None = None
    audience: str = "all_members"
    channels: list[str] = Field(default_factory=lambda: ["in_app"])
    target_role_ids: list[int] = Field(default_factory=list)
    target_levels: list[str] = Field(default_factory=list)


class AnnouncementUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=180)
    body: str | None = Field(default=None, min_length=2)
    status: str | None = None
    is_pinned: bool | None = None
    published_at: datetime | None = None
    scheduled_for: datetime | None = None
    audience: str | None = None
    channels: list[str] | None = None
    target_role_ids: list[int] | None = None
    target_levels: list[str] | None = None


class AnnouncementOut(BaseModel):
    id: int
    workspace_id: int
    title: str
    body: str
    status: str
    is_pinned: bool
    published_at: datetime | None = None
    scheduled_for: datetime | None = None
    delivered_at: datetime | None = None
    delivery_count: int = 0
    audience: str = "all_members"
    channels: list[str] = Field(default_factory=list)
    target_role_ids: list[int] = Field(default_factory=list)
    target_levels: list[str] = Field(default_factory=list)
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AuthLoginRequest(BaseModel):
    workspace_slug: str | None = None
    email: str
    password: str | None = None


class AuthLoginResponse(BaseModel):
    workspace_slug: str
    workspace_name: str
    member_id: int
    member_name: str
    member_role: str
    user_id: int | None = None
    role_key: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    workspaces: list["AuthMeWorkspace"] = Field(default_factory=list)


class AuthRegisterRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=120)
    workspace_slug: str = Field(min_length=2, max_length=120)
    university: str | None = None
    body_type: str | None = None
    faculty: str | None = None
    admin_name: str = Field(min_length=2, max_length=120)
    admin_email: str
    phone_number: str | None = None
    admin_role: str | None = None
    password: str | None = None


class AuthMeWorkspace(BaseModel):
    workspace_slug: str
    workspace_name: str
    member_id: int
    role: str
    role_key: str
    permissions: list[str]


class AuthMeResponse(BaseModel):
    user: UserOut
    workspaces: list[AuthMeWorkspace]


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None
    access_token: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=6)


class VerifyEmailRequest(BaseModel):
    token: str


class AuthStatusResponse(BaseModel):
    ok: bool = True
    message: str


class InvitationCreate(BaseModel):
    email: str
    role_id: int
    note: str | None = None


class InvitationOut(BaseModel):
    id: int
    workspace_id: int
    email: str
    role_id: int
    role_name: str
    token: str
    status: str
    email_delivery_status: str | None = None
    email_delivery_provider: str | None = None
    email_delivery_sender: str | None = None
    expires_at: datetime | None = None
    created_at: datetime


class InviteLinkCreate(BaseModel):
    role_id: int
    expires_at: datetime | None = None


class InviteLinkOut(BaseModel):
    id: int
    workspace_id: int
    role_id: int
    role_name: str
    token: str
    is_active: bool
    expires_at: datetime | None = None
    created_at: datetime


class InvitePreview(BaseModel):
    workspace_name: str
    workspace_slug: str
    email: str | None = None
    role_name: str
    expires_at: datetime | None = None


class InvitationAccept(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=6)
    phone_number: str | None = None


class InviteLinkAccept(InvitationAccept):
    email: str


class TransferOwnershipRequest(BaseModel):
    target_member_id: int
    password: str = Field(min_length=6)
    fallback_role_id: int | None = None


class TransferRoleRequest(BaseModel):
    target_member_id: int
    role_id: int
    outgoing_member_role_id: int | None = None


class IntegrationOut(BaseModel):
    provider: str
    status: str
    configured: bool
    connected_email: str | None = None
    scopes: list[str] = Field(default_factory=list)
    connected_at: datetime | None = None
    expires_at: datetime | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class GoogleOAuthStartOut(BaseModel):
    authorization_url: str


class FirefliesTranscriptImportRequest(BaseModel):
    transcript_id: str = Field(min_length=2)


class DashboardCounts(BaseModel):
    members: int
    dues_cycles: int
    events: int
    campaigns: int
    links: int
    reports: int = 0
    paid_members: int
    pending_members: int
    tasks: int = 0
    pending_tasks: int = 0
    meetings: int = 0


class RecentActivityItem(BaseModel):
    type: str
    title: str
    description: str
    created_at: datetime


class ReportMetricOut(BaseModel):
    metric_key: str
    label: str
    actual_value: str
    target_value: str | None = None
    met_target: bool | None = None
    score: float | None = None
    status: str
    operator: str | None = None
    raw_actual: float | None = None
    raw_target: float | None = None


class ReportCategorySnapshotOut(BaseModel):
    category_key: str
    title: str
    weight: float
    category_score: float
    metrics: list[ReportMetricOut] = Field(default_factory=list)


class ReportCategoryNarrativeOut(BaseModel):
    category_key: str
    title: str
    headline_verdict: str
    went_well: list[str] = Field(default_factory=list)
    underperformed: list[str] = Field(default_factory=list)
    watch_out_flag: str | None = None


class ReportRecommendationOut(BaseModel):
    data_finding: str
    action: str
    expected_outcome: str
    priority: str
    responsible_role: str


class ReportNarrativeOut(BaseModel):
    executive_summary: list[str] = Field(default_factory=list)
    period_highlights: list[str] = Field(default_factory=list)
    categories: list[ReportCategoryNarrativeOut] = Field(default_factory=list)
    recommendations: list[ReportRecommendationOut] = Field(default_factory=list)
    handover_note: list[str] = Field(default_factory=list)


class ReportSummaryOut(BaseModel):
    id: int
    workspace_id: int
    title: str
    period_start: str
    period_end: str
    period_label: str | None = None
    status: str
    overall_score: float | None = None
    overall_grade: str | None = None
    generated_at: datetime | None = None
    pdf_url: str | None = None
    created_at: datetime


class ReportDetailOut(ReportSummaryOut):
    enabled_categories: list[str] = Field(default_factory=list)
    context_notes: str | None = None
    generation_error: str | None = None
    data_snapshot: list[ReportCategorySnapshotOut] = Field(default_factory=list)
    ai_narrative: ReportNarrativeOut | None = None


class ReportGenerateRequest(BaseModel):
    title: str = Field(min_length=4, max_length=180)
    period_start: str
    period_end: str
    period_label: str | None = None
    enabled_categories: list[str] = Field(
        default_factory=lambda: ["membership", "dues", "events", "meetings", "fundraising", "communication", "ai_usage"]
    )
    context_notes: str | None = None


class WorkspaceLatestReport(BaseModel):
    id: int
    title: str
    period_label: str | None = None
    status: str
    overall_score: float | None = None
    overall_grade: str | None = None
    generated_at: datetime | None = None


class WorkspaceOverview(BaseModel):
    workspace: WorkspaceOut
    counts: DashboardCounts
    recent_events: list[EventOut]
    active_campaigns: list[CampaignOut]
    dues_cycles: list[DuesCycleOut]
    links: list[LinkOut]
    announcements: list[AnnouncementOut]
    recent_activity: list[RecentActivityItem] = Field(default_factory=list)
    latest_report: WorkspaceLatestReport | None = None


class TaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    description: str | None = None
    assigned_to_member_id: int | None = None
    due_date: str | None = None
    priority: str = "medium"
    status: str = "todo"
    linked_module: str | None = None
    linked_id: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = None
    assigned_to_member_id: int | None = None
    due_date: str | None = None
    priority: str | None = None
    status: str | None = None


class TaskOut(BaseModel):
    id: int
    workspace_id: int
    title: str
    description: str | None = None
    assigned_to_member_id: int | None = None
    assigned_to_name: str | None = None
    due_date: str | None = None
    priority: str
    status: str
    linked_module: str | None = None
    linked_id: int | None = None
    created_by_user_id: int | None = None
    created_at: datetime


class MeetingCreate(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    meeting_type: str = "general"
    scheduled_for: str
    venue: str | None = None
    virtual_link: str | None = None
    agenda: list[str] = Field(default_factory=list)
    quorum_threshold: int | None = None


class MeetingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=180)
    meeting_type: str | None = None
    scheduled_for: str | None = None
    venue: str | None = None
    virtual_link: str | None = None
    agenda: list[str] | None = None
    quorum_threshold: int | None = None
    status: str | None = None


class MeetingMinutesUpdate(BaseModel):
    summary: str | None = None
    content: str | None = None
    attendance_summary: str | None = None
    decisions: list[str] | None = None


class TranscriptUpload(BaseModel):
    transcript: str = Field(min_length=10)


class MeetingOut(BaseModel):
    id: int
    workspace_id: int
    title: str
    meeting_type: str
    scheduled_for: str
    venue: str | None = None
    virtual_link: str | None = None
    agenda: list[str] = Field(default_factory=list)
    quorum_threshold: int | None = None
    status: str
    transcript: str | None = None
    transcript_source: str | None = None
    attendee_count: int = 0
    created_by_user_id: int | None = None
    created_at: datetime


class MeetingMinutesOut(BaseModel):
    id: int
    meeting_id: int
    summary: str | None = None
    content: str | None = None
    attendance_summary: str | None = None
    decisions: list[str] = Field(default_factory=list)
    ai_status: str = "draft"
    generated_by_model: str | None = None
    generated_at: datetime | None = None
    generation_error: str | None = None
    published_at: datetime | None = None
    published_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime


class ActionItemCreate(BaseModel):
    description: str = Field(min_length=2)
    assigned_to_member_id: int | None = None
    due_date: str | None = None


class ActionItemOut(BaseModel):
    id: int
    meeting_id: int
    description: str
    assigned_to_member_id: int | None = None
    assigned_to_name: str | None = None
    due_date: str | None = None
    status: str
    generated_by: str | None = None
    created_at: datetime


class MeetingDetailOut(MeetingOut):
    minutes: MeetingMinutesOut | None = None
    action_items: list[ActionItemOut] = Field(default_factory=list)


class BudgetCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    description: str | None = None
    period_label: str | None = None


class BudgetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = None
    period_label: str | None = None
    status: str | None = None


class BudgetLineCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    planned_amount: float = Field(gt=0)
    notes: str | None = None


class ExpenditureCreate(BaseModel):
    amount: float = Field(gt=0)
    notes: str | None = None
    spent_at: str | None = None


class BudgetLineOut(BaseModel):
    id: int
    budget_id: int
    name: str
    planned_amount: float
    actual_amount: float
    notes: str | None = None
    created_at: datetime


class BudgetOut(BaseModel):
    id: int
    workspace_id: int
    name: str
    description: str | None = None
    period_label: str | None = None
    status: str
    planned_total: float
    actual_total: float
    created_at: datetime


class BudgetDetailOut(BudgetOut):
    lines: list[BudgetLineOut] = Field(default_factory=list)
