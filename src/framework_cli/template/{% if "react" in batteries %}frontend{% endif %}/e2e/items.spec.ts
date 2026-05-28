import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("items page renders and has no axe violations", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Items" })).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
