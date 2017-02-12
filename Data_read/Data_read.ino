//Motor 
int PWMA = 5; //Speed control
int DirA = 4; //Direction
int PWMB = 3; //Speed control
int DirB = 2; //Direction

int state = -1;
int count = 0;


const int delayTime = 30;

int testspeed = 100;         // change to different motor speed, according to PWM
int testspeed2 = 255;
int hhcount = 1;


void setup() {
  Serial.begin(9600);
}

void loop(){
  
  int a = analogRead(A0);
  int b = analogRead(A4);


   //Show raw picture
  Serial.print(a);  // 30 or 980
  Serial.print(",");
  Serial.println(b);  // 210 or 820 

  if(Serial.available()>0){
    
    state = Serial.read();          // Serial read from monitor
    
    switch(state){                   // different state to switch  
      
      case 'u':                      // First motor makes the brake move up
      minimumStepUp();
      break;

      case 'd':                      // First motor makes the brake move down
      minimumStepDown();
      break;

      case 'e':                      // First motor makes the brake move down slowly
      slowMinimumStepDown();
      break;

      case 'i':                      // First motor makes the brake move up slowly
      slowMinimumStepUp();
      break;

      case 's':                      // Stop first motor
      Stop();
      break;

      case 'c':                      // clear data
      //angle = 0;
      break;
    }
  }

}



void move(int motor, int speed, int direction) {  // Motor moves function

  boolean dirbool = HIGH;                         // High for clockwise movement
  if (direction == 0) { 
    dirbool = LOW;                                // Low for counterclockwise movement
  }

  if (motor == 1) {
    digitalWrite(DirA, dirbool);                  // Write first motor's direction and PWM
    analogWrite(PWMA, speed);
  }
  
  if (motor == 2) {                               // Write second motor's direction and PWM
  digitalWrite(DirB, dirbool);
  analogWrite(PWMB, speed);

  }
}

void minimumStepUp(){    // minimumStepUp

  move(1,testspeed2,1);
  delay(delayTime);
  move(1,0,0);
  
  }

void minimumStepDown(){   // minimumStepDown

  move(1,testspeed2,0);
  delay(delayTime);
  move(1,0,0);
  
  }

void slowMinimumStepDown(){   // minimumStepDown

  move(1,testspeed,0);
  delay(delayTime);
  move(1,0,0);
  
  }

void slowMinimumStepUp(){    // minimumStepUp

  move(1,testspeed,1);
  delay(delayTime);
  move(1,0,0);
  
  }
  

void Stop(){              // Stop

  move(1,0,0);
  
  }



