import { apiGet } from "@/lib/api";

type Workspace = { id: number; slug: string; name: string };
type Task = {
  id: number;
  title: string;
  assigned_to_name?: string | null;
  due_date?: string | null;
  priority: string;
  status: string;
};

export default async function TasksPage({ params }: { params: { workspaceSlug: string } }) {
  const workspace = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
  const tasks = await apiGet<Task[]>(`/workspaces/${workspace.id}/tasks`);

  return (
    <section className="page-stack">
      <header className="page-head">
        <p className="eyebrow">Tasks</p>
        <h1>Workspace tasks</h1>
        <p>{workspace.name}</p>
      </header>
      <article className="panel-card">
        {tasks.length === 0 ? (
          <div className="empty-state">
            <span className="material-symbols-outlined" aria-hidden="true">
              checklist
            </span>
            <h2>No tasks yet</h2>
            <p>Tasks will appear here, including meeting action items as you start using the module.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Assigned</th>
                  <th>Due</th>
                  <th>Priority</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => (
                  <tr key={task.id}>
                    <td>{task.title}</td>
                    <td>{task.assigned_to_name || "-"}</td>
                    <td>{task.due_date || "-"}</td>
                    <td>{task.priority}</td>
                    <td>{task.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </article>
    </section>
  );
}
