API_VERSION = "API_v1.0"
MOD_NAME = "DGLAB"


class DGLAB():
    def __init__(self):
        events.onReceiveShellInfo(self.onReceiveShellInfo)
        events.onBattleStart(self.reinit_data)
        events.onBattleEnd(self.reinit_data)
        events.onBattleQuit(self.reinit_data)
        callbacks.perTick(self.updateData)
        self.player_id = None
        self.damage = 0
        self.eatTorpedo = 0
        self.health = 1
        self.maxHealth = 1
        self.healthPercentage = 1

    def reinit_data(self, *args, **kwargs):
        self.damage = 0
        self.eatTorpedo = 0
        self.health = 1
        self.maxHealth = 1
        self.healthPercentage = 1

    def onReceiveShellInfo(self, victimID, shooterID, ammoId, matID, shotID, Booleans, damage, shotPosition, yaw, hlinfo):
        playerInfo = battle.getSelfPlayerInfo()
        self.player_id = playerInfo["id"]

        # 确定弹药类型为鱼雷并且排除航母雷
        if str(battle.getAmmoParams(ammoId)).find("Torpedo") != -1 and str(battle.getPlayerByVehicleId(shooterID)).find("IDS_AIRCARRIER") == -1:
            self.eatTorpedo = self.eatTorpedo + 1


        if shooterID == playerInfo["shipId"]:
            return
        self.damage = self.damage + damage
        

    def updateData(self):
        try:
            playerInfo = battle.getSelfPlayerInfo()
            self.health = playerInfo["shipGameData"]["health"]
            self.maxHealth = playerInfo["maxHealth"]
            self.healthPercentage = self.health / self.maxHealth
        except:
            self.reinit_data()

        with open("data.txt", "w") as f:
            f.write('{"hp_pct": ')
            f.write(str(self.healthPercentage))
            f.write(', "dmg": ')
            f.write(str(self.damage))
            f.write(', "eat_torpedo": ')
            f.write(str(self.eatTorpedo))
            f.write('}')


DGLAB_Mod = DGLAB()
# devmenu.enable()
