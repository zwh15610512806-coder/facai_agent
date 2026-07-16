import { expect, test } from "vitest";

import { canConnectNodes, nodePorts } from "./node-ports";

test("predefined generation nodes expose only typed ports", () => {
  expect(nodePorts("product_source")).toEqual(["product"]);
  expect(nodePorts("model_generation")).toEqual(["reference", "prompt", "output"]);
  expect(nodePorts("export")).toEqual(["input"]);
});

test("node connections reject incompatible source and target combinations", () => {
  expect(canConnectNodes("product_source", "auto_cutout", "product_asset")).toBe(true);
  expect(canConnectNodes("product_source", "model_generation", "product_asset")).toBe(false);
  expect(canConnectNodes("auto_cutout", "model_generation", "cutout_asset")).toBe(true);
  expect(canConnectNodes("prompt", "model_generation", "prompt")).toBe(true);
  expect(canConnectNodes("product_source", "detail_output", "product_asset")).toBe(false);
  expect(canConnectNodes("text_layer", "model_generation", "text_layer")).toBe(false);
  expect(canConnectNodes("model_generation", "main_output", "background_image")).toBe(false);
  expect(canConnectNodes("model_generation", "export", "output_image")).toBe(false);
});
