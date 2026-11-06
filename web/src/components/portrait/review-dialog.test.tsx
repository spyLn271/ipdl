import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { portrait, portraitOut } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { missingComments, ReviewDialog } from "./review-dialog";

describe("ReviewDialog", () => {
  it("requires a justification for every overridden factor", () => {
    expect(missingComments({ transactions: { level: "low", comment: "" } })).toEqual([
      "transactions",
    ]);
    expect(missingComments({ transactions: { level: "low", comment: "СПО нет" } })).toEqual([]);
    expect(missingComments({ legal: { level: "", comment: "" } })).toEqual([]);
  });

  it("blocks saving an override without a comment", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(
      <ReviewDialog
        personId="person"
        portraitId={portraitOut.meta.id}
        portrait={portrait}
        review={null}
        open
        onOpenChange={() => {}}
      />,
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: /^Финансовые операции в РК/ }),
      "low",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить решение" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Обоснование обязательно");
    expect(fetchMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
