import { screen, within } from "@testing-library/react";
import { portrait } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { FactorList } from "./factor-list";

describe("FactorList", () => {
  it("renders all eight factors with level badges", () => {
    renderWithProviders(<FactorList factors={portrait.risk.factors} />);
    const list = screen.getByRole("list");
    expect(within(list).getAllByRole("listitem")).toHaveLength(8);
    const sanctions = list.querySelector('[data-factor="sanctions"]') as HTMLElement;
    expect(within(sanctions).getByText("Санкционные списки")).toBeInTheDocument();
    expect(within(sanctions).getByText("Высокий")).toBeInTheDocument();
  });

  it("marks analyst overrides with the automatic level", () => {
    const factors = portrait.risk.factors.map((f) =>
      f.key === "transactions"
        ? { ...f, level: "low" as const, comment: "СПО не поступали", overridden: true }
        : f,
    );
    renderWithProviders(<FactorList factors={factors} />);
    expect(screen.getByText("СПО не поступали")).toBeInTheDocument();
    expect(screen.getByText(/решение аналитика/)).toHaveTextContent("автоматически: Нет данных");
  });

  it("links source references to the source list", () => {
    renderWithProviders(<FactorList factors={portrait.risk.factors} />);
    const withSources = portrait.risk.factors.find((f) => f.evidence.length > 0);
    if (withSources) {
      const id = withSources.evidence[0]!;
      expect(screen.getAllByRole("link", { name: id })[0]).toHaveAttribute("href", `#source-${id}`);
    }
  });
});
