import { Component } from '@angular/core';
import { AngularFirestore } from 'angularfire2/firestore';
import { AngularFireDatabase } from 'angularfire2/database';
import { AngularFireAuth } from 'angularfire2/auth';
import { Observable } from 'rxjs/Observable';
import * as firebase from 'firebase/app';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})

export class AppComponent {
  title = 'app';
  user: Observable<firebase.User>;
  startHr: Observable<any>;
  startMin: Observable<any>;
  endHr: Observable<any>;
  endMin: Observable<any>;
  weight : Observable<any>;
  temperature : Observable<any>;
  humidity : Observable<any>;
  
  mode:any;
  
  constructor(public afAuth: AngularFireAuth,private db: AngularFireDatabase) {
      this.afAuth.auth.signInAnonymously();
      this.user = this.afAuth.authState;
    
      this.startHr = this.db.object('startHr').valueChanges();
      this.startMin = this.db.object('startMin').valueChanges();
      this.endHr = this.db.object('endHr').valueChanges();
      this.endMin = this.db.object('endMin').valueChanges();

      this.weight = this.db.object('weight').valueChanges();
      this.temperature = this.db.object('temperature').valueChanges();
      this.humidity = this.db.object('humidity').valueChanges();
      
      this.db.object('mode').valueChanges().subscribe(x=> this.mode = x);

    }
    setTime(newStartHr,newStartMin,newEndHr,newEndMin){
      this.db.object('startHr').set(newStartHr);
      this.db.object('startMin').set(newStartMin);
      this.db.object('endHr').set(newEndHr);
      this.db.object('endMin').set(newEndMin);
    }
    turnOnOff(){
      if(this.mode==0){
        this.db.object('mode').set(1);
      }else{
        this.db.object('mode').set(0);        
      }
    }
    testOrder(val){
      var promiseFn:Promise<void> = this.db.object('testorder').set(val);

      //ให้ reset เป็น 0 เองอัตโนมัติหลังจากยิง command
      var source = Observable.fromPromise(promiseFn);
      source.delay(10000).subscribe(x=>{this.db.object('testorder').set(0)});
    }
}
