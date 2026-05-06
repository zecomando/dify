UPDATE answer_audits
SET generator_prompt_version = 'legal-deterministic-generator-v1'
WHERE generator_prompt_version IS NULL
  AND model_generator = 'deterministic-evidence-summarizer';

UPDATE answer_audits
SET validator_prompt_version = 'legal-deterministic-validator-v1'
WHERE validator_prompt_version IS NULL
  AND model_validator = 'deterministic-source-validator';
