# Signal Generation - Production Deployment Checklist

## Pre-Deployment (Must Complete Before Deploy)

### Code Quality
- [x] All unit tests passing (27/27)
- [x] All integration tests passing (3/3)
- [x] Code reviewed and approved
- [x] No critical security vulnerabilities
- [x] Error handling implemented

### Testing
- [x] Unit tests with mocks (fast feedback)
- [x] Integration tests with real data
- [x] Real eToro API tested
- [x] Real market data tested
- [x] Risk validation tested

### Infrastructure
- [ ] CI/CD pipeline configured
- [ ] Integration tests in deployment gate
- [ ] Credentials stored in secrets manager
- [ ] Monitoring configured
- [ ] Alerting configured

## Deployment Steps

### 1. Pre-Deployment Verification
```bash
# Run all tests locally
pytest tests/test_signal_generation.py -v
pytest tests/test_signal_generation_integration.py -v -m integration

# Verify all pass
echo "✅ All tests must pass before proceeding"
```

### 2. Deploy to Staging
```bash
# Deploy code to staging environment
git checkout main
git pull origin main

# Run integration tests in staging
pytest tests/test_signal_generation_integration.py -v -m integration

# Verify staging works
echo "✅ Staging must work before production deploy"
```

### 3. Deploy to Production
```bash
# Deploy to production
# (Your deployment command here)

# Verify deployment
curl https://your-api.com/health
```

### 4. Post-Deployment Verification
```bash
# Check logs for signal generation
tail -f logs/backend.log | grep "Signal"

# Verify metrics are being collected
curl https://your-api.com/metrics | grep signal_generation

# Check for errors
tail -f logs/backend.log | grep "ERROR"
```

## Post-Deployment (Complete Within 24 Hours)

### Monitoring Setup
- [ ] Add Prometheus metrics endpoint
- [ ] Configure Grafana dashboard
- [ ] Set up log aggregation
- [ ] Configure error tracking (Sentry/etc)

### Alerting Setup
- [ ] Alert: No signals generated for 1 hour (during market hours)
- [ ] Alert: Validation success rate < 50%
- [ ] Alert: Generation error rate > 10/hour
- [ ] Alert: Validation error rate > 10/hour
- [ ] Alert: System state stuck in PAUSED

### Documentation
- [ ] Update runbook with troubleshooting steps
- [ ] Document monitoring dashboard
- [ ] Document alert response procedures
- [ ] Update API documentation

## Monitoring Checklist (First 48 Hours)

### Hour 1
- [ ] Check logs for signal generation
- [ ] Verify no errors in logs
- [ ] Check metrics dashboard
- [ ] Verify signals are being generated

### Hour 4
- [ ] Review signal generation rate
- [ ] Check validation success rate
- [ ] Review confidence score distribution
- [ ] Check for any anomalies

### Hour 12
- [ ] Review full day of metrics
- [ ] Check error logs
- [ ] Verify no performance degradation
- [ ] Review signal quality

### Hour 24
- [ ] Full metrics review
- [ ] Performance analysis
- [ ] Error rate analysis
- [ ] Confidence score analysis

### Hour 48
- [ ] Week-over-week comparison
- [ ] Identify any trends
- [ ] Adjust alerting thresholds if needed
- [ ] Document any issues found

## Rollback Plan

### If Signal Generation Fails
```bash
# 1. Check logs
tail -f logs/backend.log | grep "ERROR"

# 2. Check system state
curl https://your-api.com/api/control/state

# 3. If critical, pause system
curl -X POST https://your-api.com/api/control/pause

# 4. Rollback code
git revert <commit-hash>
# Deploy previous version

# 5. Verify rollback
pytest tests/test_signal_generation_integration.py -v
```

### If Validation Fails
```bash
# 1. Check risk manager logs
tail -f logs/backend.log | grep "validation"

# 2. Check account balance
curl https://your-api.com/api/account

# 3. If needed, activate circuit breaker
# (This blocks new entries but allows exits)

# 4. Investigate and fix
# 5. Reset circuit breaker when ready
```

## Success Criteria

### Day 1
- [ ] No critical errors
- [ ] Signals being generated
- [ ] Validation working correctly
- [ ] No system crashes

### Week 1
- [ ] Validation success rate > 70%
- [ ] Average confidence score > 0.5
- [ ] Error rate < 1%
- [ ] No production incidents

### Month 1
- [ ] Stable signal generation
- [ ] Consistent validation rates
- [ ] No major issues
- [ ] Positive trading results

## Emergency Contacts

- **On-Call Engineer:** [Your contact]
- **System Owner:** [Your contact]
- **DevOps Team:** [Your contact]

## Useful Commands

### Check Signal Generation
```bash
# View recent signals
tail -100 logs/backend.log | grep "Signal generated"

# Count signals by type
grep "ENTER_LONG" logs/backend.log | wc -l
grep "EXIT_LONG" logs/backend.log | wc -l
```

### Check Validation
```bash
# View validation results
tail -100 logs/backend.log | grep "Signal validated"

# Count rejections
grep "Signal rejected" logs/backend.log | wc -l
```

### Check System Health
```bash
# System state
curl https://your-api.com/api/control/state

# Active strategies
curl https://your-api.com/api/strategies?status=DEMO

# Account info
curl https://your-api.com/api/account
```

## Notes

- Keep this checklist updated as you learn more
- Document any issues encountered
- Update runbook with solutions
- Share learnings with team
