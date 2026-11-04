import { formatMoney, luhnValid } from "./format";

describe("formatMoney", () => {
  it("COP y JPY sin decimales", () => {
    expect(formatMoney("180000", "COP")).not.toMatch(/[.,]00\b/);
    expect(formatMoney("9800", "JPY")).not.toMatch(/[.,]\d{2}$/);
  });
  it("USD con dos decimales", () => {
    expect(formatMoney("75", "USD")).toMatch(/75,00/);
  });
  it("monto ausente", () => {
    expect(formatMoney(null, "USD")).toBe("—");
  });
});

describe("luhnValid", () => {
  it("acepta tarjeta de prueba válida", () => expect(luhnValid("4242 4242 4242 4242")).toBe(true));
  it("rechaza número inválido", () => expect(luhnValid("4242 4242 4242 4241")).toBe(false));
});
