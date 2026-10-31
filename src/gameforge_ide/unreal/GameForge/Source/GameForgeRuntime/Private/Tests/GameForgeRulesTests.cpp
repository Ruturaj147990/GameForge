#include "Misc/AutomationTest.h"
#include "GameForgeRules.h"
#include "Dom/JsonObject.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGameForgeRulesCountTest, "GameForge.Kit.Rules.CountAtLeast", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FGameForgeRulesCountTest::RunTest(const FString& Parameters)
{
	FGameForgeConditionEvaluator::FContext Ctx;
	Ctx.CountEvents = [](FName Event, FName Entity) -> int32
	{
		if (Event == FName(TEXT("pickup.collected"))) return 5;
		return 0;
	};

	TSharedPtr<FJsonObject> Cond = MakeShared<FJsonObject>();
	Cond->SetStringField(TEXT("kind"), TEXT("count_at_least"));
	Cond->SetStringField(TEXT("event"), TEXT("pickup.collected"));
	Cond->SetNumberField(TEXT("n"), 3.0);

	FString Error;
	TestTrue(TEXT("Count >= 3 should pass when 5 observed"), FGameForgeConditionEvaluator::Evaluate(Cond, Ctx, Error));

	Cond->SetNumberField(TEXT("n"), 10.0);
	TestFalse(TEXT("Count >= 10 should fail when 5 observed"), FGameForgeConditionEvaluator::Evaluate(Cond, Ctx, Error));

	// Malformed (missing n)
	Cond->RemoveField(TEXT("n"));
	TestFalse(TEXT("Missing n should fail"), FGameForgeConditionEvaluator::Evaluate(Cond, Ctx, Error));
	TestTrue(TEXT("Error should be set on missing n"), !Error.IsEmpty());

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGameForgeRulesStatOperatorsTest, "GameForge.Kit.Rules.StatOperators", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FGameForgeRulesStatOperatorsTest::RunTest(const FString& Parameters)
{
	FGameForgeConditionEvaluator::FContext Ctx;
	Ctx.GetStat = [](FName Stat) -> float
	{
		if (Stat == FName(TEXT("score"))) return 50.f;
		return NAN;
	};

	auto CheckOp = [&](const FString& Op, double Target, bool bExpected)
	{
		TSharedPtr<FJsonObject> Cond = MakeShared<FJsonObject>();
		Cond->SetStringField(TEXT("kind"), TEXT("stat"));
		Cond->SetStringField(TEXT("stat"), TEXT("score"));
		Cond->SetStringField(TEXT("op"), Op);
		Cond->SetNumberField(TEXT("value"), Target);
		FString Error;
		bool Res = FGameForgeConditionEvaluator::Evaluate(Cond, Ctx, Error);
		TestEqual(FString::Printf(TEXT("Op %s vs %f"), *Op, Target), Res, bExpected);
	};

	CheckOp(TEXT("=="), 50.0, true);
	CheckOp(TEXT("=="), 50.00001, true); // within 1e-4 tolerance
	CheckOp(TEXT("=="), 51.0, false);
	CheckOp(TEXT("<="), 50.0, true);
	CheckOp(TEXT("<="), 55.0, true);
	CheckOp(TEXT("<="), 45.0, false);
	CheckOp(TEXT("<"), 55.0, true);
	CheckOp(TEXT("<"), 50.0, false);
	CheckOp(TEXT(">="), 50.0, true);
	CheckOp(TEXT(">="), 45.0, true);
	CheckOp(TEXT(">="), 55.0, false);
	CheckOp(TEXT(">"), 45.0, true);
	CheckOp(TEXT(">"), 50.0, false);

	// NaN check
	TSharedPtr<FJsonObject> NanCond = MakeShared<FJsonObject>();
	NanCond->SetStringField(TEXT("kind"), TEXT("stat"));
	NanCond->SetStringField(TEXT("stat"), TEXT("unknown_stat"));
	NanCond->SetStringField(TEXT("op"), TEXT(">="));
	NanCond->SetNumberField(TEXT("value"), 0.0);
	FString Err;
	TestFalse(TEXT("NaN stat must return false"), FGameForgeConditionEvaluator::Evaluate(NanCond, Ctx, Err));

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGameForgeRulesNestingTest, "GameForge.Kit.Rules.NestingAndDepth", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FGameForgeRulesNestingTest::RunTest(const FString& Parameters)
{
	FGameForgeConditionEvaluator::FContext Ctx;
	Ctx.GetStat = [](FName Stat) -> float { return 10.f; };

	// Valid compound 'all'
	TSharedPtr<FJsonObject> CondAll = MakeShared<FJsonObject>();
	CondAll->SetStringField(TEXT("kind"), TEXT("all"));
	TArray<TSharedPtr<FJsonValue>> SubList;

	TSharedPtr<FJsonObject> C1 = MakeShared<FJsonObject>();
	C1->SetStringField(TEXT("kind"), TEXT("stat"));
	C1->SetStringField(TEXT("stat"), TEXT("a"));
	C1->SetStringField(TEXT("op"), TEXT("=="));
	C1->SetNumberField(TEXT("value"), 10.0);
	SubList.Add(MakeShared<FJsonValueObject>(C1));

	CondAll->SetArrayField(TEXT("conditions"), SubList);

	FString Error;
	TestTrue(TEXT("Single all condition passes"), FGameForgeConditionEvaluator::Evaluate(CondAll, Ctx, Error));

	// Empty all condition is malformed
	TSharedPtr<FJsonObject> EmptyAll = MakeShared<FJsonObject>();
	EmptyAll->SetStringField(TEXT("kind"), TEXT("all"));
	EmptyAll->SetArrayField(TEXT("conditions"), TArray<TSharedPtr<FJsonValue>>());
	TestFalse(TEXT("Empty all condition is malformed"), FGameForgeConditionEvaluator::Evaluate(EmptyAll, Ctx, Error));

	// Depth > 3 guard
	TSharedPtr<FJsonObject> D0 = MakeShared<FJsonObject>();
	D0->SetStringField(TEXT("kind"), TEXT("all"));
	TSharedPtr<FJsonObject> D1 = MakeShared<FJsonObject>();
	D1->SetStringField(TEXT("kind"), TEXT("all"));
	TSharedPtr<FJsonObject> D2 = MakeShared<FJsonObject>();
	D2->SetStringField(TEXT("kind"), TEXT("all"));
	TSharedPtr<FJsonObject> D3 = MakeShared<FJsonObject>();
	D3->SetStringField(TEXT("kind"), TEXT("all"));
	TSharedPtr<FJsonObject> D4 = MakeShared<FJsonObject>();
	D4->SetStringField(TEXT("kind"), TEXT("stat"));
	D4->SetStringField(TEXT("stat"), TEXT("a"));
	D4->SetStringField(TEXT("op"), TEXT("=="));
	D4->SetNumberField(TEXT("value"), 10.0);

	TArray<TSharedPtr<FJsonValue>> Arr4; Arr4.Add(MakeShared<FJsonValueObject>(D4));
	D3->SetArrayField(TEXT("conditions"), Arr4);
	TArray<TSharedPtr<FJsonValue>> Arr3; Arr3.Add(MakeShared<FJsonValueObject>(D3));
	D2->SetArrayField(TEXT("conditions"), Arr3);
	TArray<TSharedPtr<FJsonValue>> Arr2; Arr2.Add(MakeShared<FJsonValueObject>(D2));
	D1->SetArrayField(TEXT("conditions"), Arr2);
	TArray<TSharedPtr<FJsonValue>> Arr1; Arr1.Add(MakeShared<FJsonValueObject>(D1));
	D0->SetArrayField(TEXT("conditions"), Arr1);

	TestFalse(TEXT("Depth 4 should fail depth guard"), FGameForgeConditionEvaluator::Evaluate(D0, Ctx, Error));
	TestTrue(TEXT("Error contains depth warning"), Error.Contains(TEXT("depth")));

	return true;
}

#endif
