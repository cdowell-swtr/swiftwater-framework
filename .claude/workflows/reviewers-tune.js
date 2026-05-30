export const meta = {
  name: 'reviewers-tune',
  description: 'Fan out per-(agent × fixture × repeat) calls via the split-manifest pattern.',
  phases: [
    { title: 'Load', detail: 'load the per-item index' },
    { title: 'Tune', detail: 'one subagent call per item, in parallel' },
  ],
}

// The Workflow tool delivers `args` as either a parsed object or a JSON string,
// depending on the caller. Normalize to an object so the rest of the script is
// invariant to how the slash command (or a direct invocation) passed args.
const ARGS = typeof args === 'string' ? JSON.parse(args) : args
const indexPath = ARGS.indexPath
const itemsDir = ARGS.itemsDir
if (!indexPath || !itemsDir) {
  throw new Error('reviewers-tune: args.indexPath and args.itemsDir are required')
}

phase('Load')

const INDEX_SCHEMA = {
  type: 'object',
  required: ['items'],
  properties: {
    items: {
      type: 'array',
      items: {
        type: 'object',
        required: ['i', 'agent', 'kind', 'case', 'repeat_idx', 'subagent_type'],
        properties: {
          i: { type: 'integer' },
          agent: { type: 'string' },
          kind: { type: 'string' },
          case: { type: 'string' },
          repeat_idx: { type: 'integer' },
          subagent_type: { type: 'string' },
          seeded_file: { type: ['string', 'null'] },
        },
      },
    },
  },
}

const index = await agent(
  `Read the JSON file at ${indexPath} and return it. Structure: {"items": [...]}.`,
  { label: 'load-index', phase: 'Load', schema: INDEX_SCHEMA, agentType: 'general-purpose' }
)
const items = index.items

phase('Tune')

const FINDINGS_SCHEMA = {
  type: 'object',
  required: ['findings'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['path', 'line', 'severity', 'message'],
        properties: {
          path: { type: 'string' },
          line: { type: 'integer' },
          severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low', 'info'] },
          message: { type: 'string' },
          suggestion: { type: ['string', 'null'] },
        },
      },
    },
  },
}

// Per-item dispatch: each subagent reads its own item file, constructs the reviewer
// prompt from the system_blocks + user_message, and returns findings.
const ITEM_PROMPT = (path) => `
You are acting as a code reviewer. Your inputs live in a JSON file on disk.

1. Read the JSON file at ${path}. It has fields:
   - system_blocks: array of {text} — these together form the system context for the reviewer
     (typically a unified diff, optionally bundled context files, and the reviewer's prompt).
   - user_message: string — the final user instruction (typically "Return your findings as a JSON array only.").
   - tools_allowed: array of strings or null. If non-null, use ONLY those tools.
   - root_dir: string — when present, all tool paths should be ABSOLUTE paths starting with this root.

2. Concatenate the text of every system_block with double newlines as your effective system context.
   Treat this as your operating identity and instructions.

3. Execute the review as that reviewer would. If tools_allowed is non-null (an agentic reviewer),
   you may use the listed tools to explore the code under root_dir; use absolute paths only.

4. Return a JSON object: {"findings": [...]} where findings is the JSON array the reviewer would
   produce (each finding has path/line/severity/message and optional suggestion). If no issues,
   return {"findings": []}. The response will be schema-validated.
`

const results = await parallel(items.map((item) => async () => {
  const itemPath = `${itemsDir}/item-${String(item.i).padStart(4, '0')}.json`
  const label = `${item.agent}/${item.kind}/${item.case}__r${item.repeat_idx}`
  try {
    const out = await agent(ITEM_PROMPT(itemPath), {
      label,
      phase: 'Tune',
      schema: FINDINGS_SCHEMA,
      agentType: item.subagent_type,
    })
    return {
      agent: item.agent,
      kind: item.kind,
      case: item.case,
      repeat_idx: item.repeat_idx,
      seeded_file: item.seeded_file,
      findings: out.findings,
      // Workflow-level instrumentation: usage/latency/etc are not captured here
      // (the agent() return is just the validated schema). Future improvement.
      usage: {},
      latency_ms: null,
      stop_reason: 'end_turn',
      raw_text: JSON.stringify(out.findings),
      turns: 1,
      tool_calls: [],
    }
  } catch (e) {
    log(`item ${item.i} (${label}) failed: ${e.message}`)
    return null
  }
}))

return { results: results.filter(Boolean), meta: ARGS.meta || {} }
