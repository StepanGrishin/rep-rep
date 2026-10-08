def common_opponent_details(state, player_a, player_b):
    result = []

    common = state.common_opponents(
        player_a,
        player_b,
    )

    for opponent in common:
        a_wins = a_losses = 0
        b_wins = b_losses = 0

        for opp, surface, won in state.player(
            player_a
        ).opponents:
            if opp == opponent:
                if won:
                    a_wins += 1
                else:
                    a_losses += 1

        for opp, surface, won in state.player(
            player_b
        ).opponents:
            if opp == opponent:
                if won:
                    b_wins += 1
                else:
                    b_losses += 1

        result.append({
            "opponent": opponent,
            "a_wins": a_wins,
            "a_losses": a_losses,
            "b_wins": b_wins,
            "b_losses": b_losses,
        })

    return result
