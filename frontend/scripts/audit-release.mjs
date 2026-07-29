import { spawnSync } from 'node:child_process';

const allowedAdvisories = new Set([
  'https://github.com/advisories/GHSA-qwww-vcr4-c8h2',
]);
const allowedPackages = new Set(['react-router', 'react-router-dom']);

const auditArguments = ['audit', '--omit=dev', '--json'];
const npmExecPath = process.env.npm_execpath;
const result = npmExecPath
  ? spawnSync(process.execPath, [npmExecPath, ...auditArguments], { encoding: 'utf8' })
  : spawnSync(
      process.platform === 'win32' ? 'npm.cmd' : 'npm',
      auditArguments,
      { encoding: 'utf8' },
    );

if (!result.stdout) {
  process.stderr.write(
    result.error?.message
    || result.stderr
    || 'npm audit did not return JSON\n',
  );
  process.exit(1);
}

let report;
try {
  report = JSON.parse(result.stdout);
} catch {
  process.stderr.write(result.stdout);
  process.stderr.write(result.stderr || '');
  process.exit(1);
}

const vulnerabilities = Object.values(report.vulnerabilities || {});
if (vulnerabilities.length === 0) {
  console.log('No production npm vulnerabilities found.');
  process.exit(0);
}

const unexpectedPackages = vulnerabilities
  .map(vulnerability => vulnerability.name)
  .filter(name => !allowedPackages.has(name));
const advisoryUrls = vulnerabilities.flatMap(vulnerability =>
  vulnerability.via
    .filter(item => typeof item === 'object' && item.url)
    .map(item => item.url)
);
const unexpectedAdvisories = advisoryUrls.filter(url => !allowedAdvisories.has(url));

if (
  unexpectedPackages.length > 0
  || unexpectedAdvisories.length > 0
  || advisoryUrls.length === 0
) {
  process.stderr.write(result.stdout);
  process.exit(1);
}

console.warn(
  'Only the documented React Router RSC advisory remains. '
  + 'Breachwright does not use React Server Components or React Router framework mode.',
);
