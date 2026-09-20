import { readFile } from 'node:fs/promises';

import { Parser, fromFile } from '@asyncapi/parser';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

const asyncApiPath = 'contracts/asyncapi.yaml';
const scheduleSchemaPath = 'contracts/schemas/work-stage-import.schema.json';
const scheduleExamplePath = 'contracts/examples/work-stage-import.json';

const parser = new Parser();
const { document, diagnostics } = await fromFile(parser, asyncApiPath).parse();
const asyncApiErrors = diagnostics.filter((diagnostic) => diagnostic.severity === 0);

if (!document || asyncApiErrors.length > 0) {
  for (const diagnostic of asyncApiErrors) {
    const path = diagnostic.path?.join('.') ?? '<root>';
    console.error(`${asyncApiPath}:${path}: ${diagnostic.message}`);
  }
  process.exitCode = 1;
}

const [scheduleSchema, scheduleExample] = await Promise.all([
  readJson(scheduleSchemaPath),
  readJson(scheduleExamplePath)
]);
const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);
const validateSchedule = ajv.compile(scheduleSchema);

if (!validateSchedule(scheduleExample)) {
  for (const error of validateSchedule.errors ?? []) {
    console.error(`${scheduleExamplePath}${error.instancePath}: ${error.message}`);
  }
  process.exitCode = 1;
}

if (process.exitCode !== 1) {
  console.log('AsyncAPI and schedule JSON Schema contracts are valid.');
}

async function readJson(path) {
  return JSON.parse(await readFile(path, 'utf8'));
}
