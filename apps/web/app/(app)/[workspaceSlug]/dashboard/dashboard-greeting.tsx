"use client";

import { useEffect, useMemo, useState } from "react";

import { readSession } from "@/lib/session";

export default function DashboardGreeting({
  workspaceName,
  workspaceDescription,
}: {
  workspaceName: string;
  workspaceDescription?: string;
}) {
  const [memberName, setMemberName] = useState("");

  useEffect(() => {
    setMemberName(readSession()?.member_name || "");
  }, []);

  const greeting = useMemo(() => {
    const hour = new Date().getHours();
    if (hour < 12) {
      return "Good morning";
    }
    if (hour < 17) {
      return "Good afternoon";
    }
    return "Good evening";
  }, []);

  const dateLabel = useMemo(
    () =>
      new Intl.DateTimeFormat("en-GB", {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
      }).format(new Date()),
    [],
  );

  const firstName = memberName.split(" ").filter(Boolean)[0];

  return (
    <header className="dashboard-greeting">
      <h1>
        {greeting}
        {firstName ? `, ${firstName}` : ""}
      </h1>
      <p>
        {dateLabel} · {workspaceName}
      </p>
      {workspaceDescription ? <span>{workspaceDescription}</span> : null}
    </header>
  );
}
