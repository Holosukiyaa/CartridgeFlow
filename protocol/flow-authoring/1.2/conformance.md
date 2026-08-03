# CF-FARP@1.1 - Conformance requirements

This file is a normative module of CF-FARP@1.1. The release is defined only by the same-version modules listed in README and CARTRIDGEFLOW-BASE@0.3.

## Prohibitions

The Base MUST NOT hard-code a cartridge's business behavior or supplier integration. A cartridge MUST NOT contain local URLs, credentials, tokens or private paths. An AI decision MUST NOT execute a side effect directly. A component MUST NOT execute arbitrary code, call a model, tool or network directly, select an execution target, or bypass the Host action boundary.

The Runner MUST NOT infer topology from node names, canvas layout, text, a derived relation or a stale report. It MUST NOT replay an unknown side effect without explicit confirmation. It MUST NOT mark a run or delivery successful when required output, authorization, conformance evidence or the current source digest is missing.

## Required evidence

Certification requires a machine-generated report proving all of the following:

- the Manifest declares `CARTRIDGEFLOW-BASE@0.3` and `CF-FARP@1.1`;
- the Base declares every required profile, capability and tool pack with implementation evidence;
- every process node has stable identity and structured input/output contracts;
- the execution plan compiles and has passing positive and negative tests for sequence, fork, all/any/keyed join, loop, batch, wait, failure, cancellation and recovery;
- required data is available on every reachable path and all external tools/resources are declared and preflighted;
- interaction components, Portable DLC, assets and permissions pass their isolation, hash and ownership checks;
- Analyzer reports match the current source digest and requested gate;
- the Base trusts and supports `CF-TUNING@1.0`, every tuning patch stays inside the allowed node-local field set, and immutable revision/release digests verify;
- production, package and publish targets use a published recipe snapshot, while each Run records release and materialization provenance;
- primary delivery, checkpoints, error identity, replay safety and portability checks pass.

The certification label is `cf-farp-1-1-certified`. It is issued only for the exact cartridge revision, tuning release, Base implementation, capability set and test environment named in the report. Changing any covered authoring fact or active recipe release invalidates certification.

## Minimal example

```json
{
  "protocol": {"id": "CF-FARP", "version": "1.1"},
  "states": {
    "start": {"type": "control"},
    "deliver": {
      "type": "process",
      "kind": "delivery",
      "executor": "deterministic",
      "effect": "writes_store",
      "inputs": {"report": {"binding": "store:approved_report", "required": true}},
      "outputs": {"delivery": {"identity": "store:final_delivery"}}
    },
    "done": {"type": "terminal"}
  },
  "execution_plan": {
    "schema": "cartridgeflow.execution_plan.v1",
    "entry": "start",
    "edges": [
      {"id": "start_deliver", "kind": "sequence", "from": "start", "to": "deliver"},
      {"id": "deliver_done", "kind": "sequence", "from": "deliver", "to": "done"}
    ]
  }
}
```

This example is structural only. A conforming cartridge additionally supplies the Manifest, schemas, resources, capability requirements, analysis report and test evidence required by this release.
