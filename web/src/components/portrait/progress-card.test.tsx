import { screen } from "@testing-library/react";
import { type PortraitMeta } from "@/lib/api/schemas";
import { renderWithProviders } from "@/test/render";
import { ProgressCard } from "./progress-card";

const meta: PortraitMeta = {
  id: "p1",
  version: 2,
  status: "running",
  stage: "extract",
  progress: 64,
  error: null,
  created_at: "2026-10-27T21:00:00Z",
  started_at: "2026-10-27T21:00:01Z",
  finished_at: null,
  reviewed_at: null,
  created_by_name: null,
  score: null,
  level: null,
};

describe("ProgressCard", () => {
  it("shows the percentage and the current pipeline stage", () => {
    renderWithProviders(<ProgressCard meta={meta} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "64");
    const current = screen.getByText("Извлечение фактов языковой моделью").closest("li");
    expect(current).toHaveAttribute("aria-current", "step");
    expect(screen.getByText(/Версия 2/)).toBeInTheDocument();
  });

  it("explains a queued task", () => {
    renderWithProviders(
      <ProgressCard meta={{ ...meta, status: "queued", stage: null, progress: 0 }} />,
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByText(/Задача в очереди/)).toBeInTheDocument();
  });
});
