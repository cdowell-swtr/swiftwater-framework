import { useEffect, useState } from "react";

import { fetchItems, type Item } from "./api";

export function Items() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetchItems()
      .then(setItems)
      .catch(() => setError(true));
  }, []);

  if (error) return <p role="alert">Failed to load items.</p>;
  if (items === null) return <p>Loading…</p>;
  if (items.length === 0) return <p>No items yet.</p>;
  return (
    <ul aria-label="items">
      {items.map((i) => (
        <li key={i.id}>{i.name}</li>
      ))}
    </ul>
  );
}
