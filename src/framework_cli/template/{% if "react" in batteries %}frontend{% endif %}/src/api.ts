export type Item = { id: number; name: string };

export async function fetchItems(): Promise<Item[]> {
  const res = await fetch("/items");
  if (!res.ok) throw new Error(`items request failed: ${res.status}`);
  return (await res.json()) as Item[];
}
