import PrintReportClient from "./print-report-client";

export default function ReportPrintPage({
  params,
}: {
  params: { workspaceSlug: string; reportId: string };
}) {
  return <PrintReportClient params={params} />;
}
