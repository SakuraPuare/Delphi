import { createBrowserRouter, RouterProvider } from "react-router";
import { AppLayout } from "@/components/layout/AppLayout";
import { DashboardPage } from "@/pages/dashboard/DashboardPage";
import { ProjectListPage } from "@/pages/projects/ProjectListPage";
import { ProjectNewPage } from "@/pages/projects/ProjectNewPage";
import { ProjectLayout } from "@/pages/projects/ProjectLayout";
import { OverviewTab } from "@/pages/projects/OverviewTab";
import { ImportTab } from "@/pages/projects/ImportTab";
import { GraphTab } from "@/pages/projects/GraphTab";
import { FinetuneTab } from "@/pages/projects/FinetuneTab";
import { PipelineTab } from "@/pages/projects/PipelineTab";
import { ProjectSettingsTab } from "@/pages/projects/ProjectSettingsTab";
import { ChatPage } from "@/pages/chat/ChatPage";
import { SchedulerPage } from "@/pages/scheduler/SchedulerPage";
import { ModelsPage } from "@/pages/models/ModelsPage";
import { SettingsPage } from "@/pages/settings/SettingsPage";

const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "projects", element: <ProjectListPage /> },
      { path: "projects/new", element: <ProjectNewPage /> },
      {
        path: "projects/:name",
        element: <ProjectLayout />,
        children: [
          { index: true, element: <OverviewTab /> },
          { path: "overview", element: <OverviewTab /> },
          { path: "import", element: <ImportTab /> },
          { path: "chat", element: <ChatPage /> },
          { path: "pipeline", element: <PipelineTab /> },
          { path: "graph", element: <GraphTab /> },
          { path: "finetune", element: <FinetuneTab /> },
          { path: "settings", element: <ProjectSettingsTab /> },
        ],
      },
      { path: "chat", element: <ChatPage /> },
      { path: "chat/:conversationId", element: <ChatPage /> },
      { path: "scheduler", element: <SchedulerPage /> },
      { path: "models", element: <ModelsPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
