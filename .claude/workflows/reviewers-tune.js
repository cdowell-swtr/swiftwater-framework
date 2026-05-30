export const meta = {
  name: 'reviewers-tune',
  description: 'Fan out (agent × fixture × repeat) calls to subagents and return per-call findings.',
  phases: [
    { title: 'Tune', detail: 'one subagent call per work item, in parallel' },
  ],
}

phase('Tune')

const items = args.work_items
if (!Array.isArray(items) || items.length === 0) {
  throw new Error('reviewers-tune: args.work_items must be a non-empty array')
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

const results = await parallel(items.map((item, idx) => async () => {
  const sys = item.system_blocks.map(b => b.text).join('\n\n')
  const prompt = `${sys}\n\n${item.user_message}`
  const label = `${item.agent}/${item.kind}/${item.case}__r${item.repeat_idx}`
  try {
    const out = await agent(prompt, {
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
    log(`agent call failed for ${label}: ${e.message}`)
    return null
  }
}))

return { results: results.filter(Boolean), meta: args.meta || {} }
