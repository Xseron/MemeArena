from rest_framework import serializers
from .models import GameRoom, Meme, Vote, Situation

class GameRoomSerializers(serializers.ModelSerializer):
    class Meta:
        model = GameRoom
        fields = '__all__'

class MemeSerializers(serializers.ModelSerializer):
    class Meta:
        model = Meme
        fields = '__all__'

class VoteSerializers(serializers.ModelSerializer):
    class Meta:
        model = Vote
        fields = '__all__'

class SituationSerializers(serializers.ModelSerializer):
    class Meta:
        model = Situation
        fields = '__all__'
    