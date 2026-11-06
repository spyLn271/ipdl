import { screen } from "@testing-library/react";
import { portrait } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { RiskScoreCard } from "./risk-score-card";

describe("RiskScoreCard", () => {
  it("shows the score, level and floors from the methodology", () => {
    renderWithProviders(<RiskScoreCard risk={portrait.risk} />);
    expect(screen.getByRole("heading", { name: "Итоговая оценка риска" })).toBeInTheDocument();
    expect(
      screen.getByRole("img", {
        name: `Оценка риска ${portrait.risk.score} из 100, уровень Высокий`,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Уровень: Высокий")).toBeInTheDocument();
    expect(screen.getByText("Низкий 0–33")).toBeInTheDocument();
    expect(screen.getByText(/Минимальный уровень: Возможное совпадение/)).toBeInTheDocument();
  });

  it("is localised", () => {
    renderWithProviders(
      <RiskScoreCard risk={{ ...portrait.risk, level: "low", score: 12, floors: [] }} />,
      {
        locale: "en",
      },
    );
    expect(screen.getByText("Level: Low")).toBeInTheDocument();
    expect(screen.getByText("High 67–100")).toBeInTheDocument();
  });
});
