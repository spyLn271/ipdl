import en from "../../messages/en.json";
import kk from "../../messages/kk.json";
import ru from "../../messages/ru.json";

function keys(value: object, prefix = ""): string[] {
  return Object.entries(value).flatMap(([key, v]) =>
    typeof v === "object" && v !== null ? keys(v, `${prefix}${key}.`) : [`${prefix}${key}`],
  );
}

describe("translations", () => {
  it("have the same keys in ru, kk and en", () => {
    const reference = keys(ru).sort();
    expect(keys(kk).sort()).toEqual(reference);
    expect(keys(en).sort()).toEqual(reference);
  });
});
