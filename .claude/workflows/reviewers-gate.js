export const meta = {
  name: 'reviewers-gate',
  description: 'Affected-only audit dispatched by /reviewers:gate before commits.',
  phases: [
    { title: 'Gate', detail: 'one subagent call per affected agent, in parallel' },
  ],
}

phase('Gate')

// The Workflow tool delivers `args` as either a parsed object or a JSON string,
// depending on the caller. Normalize to an object so the rest of the script is
// invariant to how the slash command (or a direct invocation) passed args.
const ARGS = typeof args === 'string' ? JSON.parse(args) : args
const items = ARGS.work_items
if (!Array.isArray(items)) {
  throw new Error('reviewers-gate: args.work_items must be an array')
}
if (items.length === 0) {
  // No affected agents → trivial PASS (the caller handles the noop case).
  return { results: [], meta: ARGS.meta || {} }
}

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

const results = await parallel(items.map((item) => async () => {
  const sys = item.system_blocks.map(b => b.text).join('\n\n')
  const prompt = `${sys}\n\n${item.user_message}`
  const label = `gate:${item.agent}`
  try {
    const out = await agent(prompt, {
      label,
      phase: 'Gate',
      schema: FINDINGS_SCHEMA,
      agentType: item.subagent_type,
    })
    return {
      agent: item.agent,
      findings: out.findings,
      usage: {},
      latency_ms: null,
      stop_reason: 'end_turn',
      raw_text: JSON.stringify(out.findings),
      turns: 1,
      tool_calls: [],
    }
  } catch (e) {
    log(`gate agent call failed for ${label}: ${e.message}`)
    return null
  }
}))

return { results: results.filter(Boolean), meta: ARGS.meta || {} }
