from action_py import (
    Action,
    ActionResult,
    EQ,
    ExecutionContext,
    ExecutionStatus,
    Plan,
    PlanExecutor,
    SET,
    WorldState,
)


def test_executor_starts_callbacks_and_updates_belief():
    first = Action("first", EQ("ready"), SET("first_done", True))
    second = Action("second", EQ("first_done"), SET("second_done", True))
    executor = PlanExecutor(
        Plan([first, second]),
        WorldState({"ready": True, "first_done": False}),
    )
    started = []

    def callback(context: ExecutionContext) -> ExecutionStatus:
        started.append((context.index, context.action.name))
        return ExecutionStatus.SUCCESS

    executor.on_start("first", callback)
    executor.on_start("second", callback)

    assert executor.tick() == ExecutionStatus.RUNNING
    assert executor.belief.get("first_done") is True

    assert executor.tick() == ExecutionStatus.SUCCESS
    assert executor.belief.get("second_done") is True
    assert started == [(0, "first"), (1, "second")]


def test_running_action_can_be_completed_externally_with_observations():
    action = Action("move", EQ("ready"), SET("at_goal", True))
    executor = PlanExecutor(Plan([action]), WorldState({"ready": True}))
    starts = []

    def start_move(context: ExecutionContext) -> ExecutionStatus:
        starts.append(context.action.name)
        return ExecutionStatus.RUNNING

    executor.on_start("move", start_move)

    assert executor.tick() == ExecutionStatus.RUNNING
    assert executor.tick() == ExecutionStatus.RUNNING
    assert starts == ["move"]
    assert executor.belief.get("at_goal") is None

    status = executor.complete_current(
        ExecutionStatus.SUCCESS,
        facts={"sensor_confirmed": True},
    )

    assert status == ExecutionStatus.SUCCESS
    assert executor.belief.get("at_goal") is True
    assert executor.belief.get("sensor_confirmed") is True


def test_running_callback_can_finish_action_on_later_tick():
    action = Action("charge", EQ("plugged_in"), SET("charged", True))
    executor = PlanExecutor(Plan([action]), WorldState({"plugged_in": True}))

    executor.on_start("charge", lambda _context: ExecutionStatus.RUNNING)
    executor.on_running("charge", lambda context: context.success())

    assert executor.tick() == ExecutionStatus.RUNNING
    assert executor.tick() == ExecutionStatus.SUCCESS
    assert executor.belief.get("charged") is True


def test_callback_observed_facts_override_model_effects_on_success():
    action = Action("inspect", EQ("ready"), SET("door_open", True))
    executor = PlanExecutor(Plan([action]), WorldState({"ready": True}))

    executor.on_start(
        "inspect",
        lambda _context: ActionResult(
            ExecutionStatus.SUCCESS,
            facts={"door_open": False, "jammed": True},
        ),
    )

    assert executor.tick() == ExecutionStatus.SUCCESS
    assert executor.belief.get("door_open") is False
    assert executor.belief.get("jammed") is True


def test_precondition_failure_fails_without_starting_callback():
    action = Action("unsafe", EQ("ready"), SET("done", True))
    executor = PlanExecutor(Plan([action]), WorldState({"ready": False}))
    started = []

    executor.on_start("unsafe", lambda context: started.append(context.action.name))

    assert executor.tick() == ExecutionStatus.FAILED
    assert executor.tick() == ExecutionStatus.FAILED
    assert started == []


def test_failed_callback_can_update_belief_for_replanning():
    action = Action("open_door", EQ("ready"), SET("door_open", True))
    executor = PlanExecutor(Plan([action]), WorldState({"ready": True}))

    executor.on_start(
        "open_door",
        lambda context: context.failed(facts={"door_blocked": True}),
    )

    assert executor.tick() == ExecutionStatus.FAILED
    assert executor.belief.get("door_open") is None
    assert executor.belief.get("door_blocked") is True


def test_failure_string_is_accepted_as_failed_status():
    assert ExecutionStatus.coerce("failure") == ExecutionStatus.FAILED
    assert ExecutionStatus.coerce("FAILED") == ExecutionStatus.FAILED
