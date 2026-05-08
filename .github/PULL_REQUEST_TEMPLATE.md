## Summary

<!-- Briefly describe what this PR does -->

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Refactor / performance
- [ ] Test coverage

## Testing

<!-- Describe how you tested this change -->

- [ ] `mvn test` passes (Java)
- [ ] `pytest -q tests` passes (Python)
- [ ] `npm run build` passes (Frontend)
- [ ] Manual testing done

## Related Issues

<!-- Link to any related issues -->

Closes #

## Checklist

- [ ] I have added/updated tests for this change
- [ ] I have updated documentation if needed (`docs/` or `README.md`)
- [ ] I have followed the existing code style (Java: Lombok + MyBatis Plus patterns; Python: PEP 8 + type hints; Vue: Composition API + Tailwind)
- [ ] New DB migrations follow Flyway rules (new V58+ script, no modification to existing V1–V57 migrations)
- [ ] Environment variables documented in `docs/ENVIRONMENT.md` or `.env.example`
